from __future__ import absolute_import, print_function

import os
import subprocess
import sys
import re

from .core import JuliaNotFound, _enviorn, which
from .find_libpython import linked_libpython


class PyCallInstallError(RuntimeError):
    def __init__(self, op, output=None):
        self.op = op
        self.output = output

    def __str__(self):
        if self.output:
            return "{} PyCall failed with output:\n\n{}".format(self.op, self.output)
        else:
            return """\
{} PyCall failed.

** Important information from Julia may be printed before Python's Traceback **

Some useful information may also be stored in the build log file
`~/.julia/packages/PyCall/*/deps/build.log`.
""".format(
                self.op
            )


def _julia_version(julia):
    output = subprocess.check_output(["julia", "--version"], universal_newlines=True)
    match = re.search(r"([0-9]+)\.([0-9]+)\.([0-9]+)", output)
    if match:
        return tuple(int(match.group(i + 1)) for i in range(3))
    else:
        return (0, 0, 0)


def install(julia="julia", color="auto", env=None, python=None, quiet=False):
    """
    install(*, julia="julia", color="auto")
    Install Julia packages required by PyJulia in `julia`.

    This function installs and/or re-builds PyCall if necessary.  It
    also makes sure to build PyCall in a way compatible with this
    Python executable (if possible).

    Keyword Arguments
    -----------------
    julia : str
        Julia executable (default: "julia")
    color : "auto", False or True
        Use colorful output if `True`.  "auto" (default) to detect it
        automatically.
    """
    if which(julia) is None:
        raise JuliaNotFound(julia, kwargname="julia")

    libpython = linked_libpython() or ""

    env = env or _enviorn.copy()

    julia_cmd = [julia, "--startup-file=no"]
    if quiet:
        color = False
    if color == "auto":
        color = sys.stdout.isatty()
    if color:
        # `--color=auto` doesn't work?
        julia_cmd.append("--color=yes")
        """
        if _julia_version(julia) >= (1, 1):
            julia_cmd.append("--color=auto")
        else:
            julia_cmd.append("--color=yes")
        """

    OP = "build" if python else "install"
    install_cmd = julia_cmd + [
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "install.jl"),
        "--",
        OP,
        python or sys.executable,
        libpython,
    ]

    kwargs = dict(env=env)
    if quiet:
        kwargs.update(
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True
        )
    proc = subprocess.Popen(install_cmd, **kwargs)
    output, _ = proc.communicate()
    returncode = proc.returncode

    if returncode == 113:  # code_no_precompile_needed
        return
    elif returncode != 0:
        raise PyCallInstallError("Installing", output)

    if not quiet:
        print(file=sys.stderr)
        print("Precompiling PyCall...", file=sys.stderr)
        sys.stderr.flush()
    precompile_cmd = julia_cmd + ["-e", "using PyCall"]
    returncode = subprocess.call(precompile_cmd, env=env)
    if returncode != 0:
        raise PyCallInstallError("Precompiling")


def make_receiver(io):
    def receiver(s):
        io.write(s)
        io.flush()

    return receiver


def redirect_output_streams():
    """
    Redirect Julia's stdout and stderr to Python's counter parts.
    """

    from .Main._PyJuliaHelper.IOPiper import pipe_std_outputs

    pipe_std_outputs(make_receiver(sys.stdout), make_receiver(sys.stderr))

    # TODO: Invoking `redirect_output_streams()` in terminal IPython
    # terminates the whole Python process.  Find out why.
