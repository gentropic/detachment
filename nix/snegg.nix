# snegg — Peter Hutterer's pure-Python wrapper around libei (not on PyPI; lives on freedesktop
# GitLab). It dlopens libei via ctypes at runtime, so there's no build/import-time dep on the .so;
# consumers put libei on LD_LIBRARY_PATH (see package.nix).
{ buildPythonPackage, setuptools, fetchFromGitLab }:
buildPythonPackage {
  pname = "snegg";
  version = "0.1.0-unstable-2026-07-05";
  pyproject = true;

  src = fetchFromGitLab {
    domain = "gitlab.freedesktop.org";
    owner = "libinput";
    repo = "snegg";
    rev = "96eb8539a044f420d73e0fe20800d815f107821a";
    sha256 = "1wlaqssvxa8qlnzip03amf964swpaghj1p25h8q6csq2jc9zsgi1";
  };

  build-system = [ setuptools ];

  # importing snegg dlopens libei, which isn't present in the sandbox — nothing to check here.
  doCheck = false;
  pythonImportsCheck = [ ];

  meta.description = "Pure-Python wrapper around the libei emulated-input library";
}
