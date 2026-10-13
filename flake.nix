{
  description = "cbrm — BERO HOST management: the customer panel and its VNC console";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }:
    let forAll = f: nixpkgs.lib.genAttrs [ "x86_64-linux" "aarch64-linux" ] (s: f nixpkgs.legacyPackages.${s});
    in {
      packages = forAll (pkgs: rec {
        cbrm = pkgs.python3Packages.buildPythonApplication {
          pname = "cbrm"; version = "0.3.2"; pyproject = true; src = ./.;
          build-system = [ pkgs.python3Packages.hatchling ];
          dependencies = with pkgs.python3Packages; [ httpx selectolax websockets vncdotool pillow mcp fastapi uvicorn ];
          nativeCheckInputs = [ pkgs.python3Packages.pytestCheckHook ];
          pythonImportsCheck = [ "cbrm" ];
          meta.license = with pkgs.lib.licenses; [ lgpl3Only ];  # WITH LGPL-3.0-linking-exception, see LICENSE.md
        };
        default = cbrm;
      });
      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [ (pkgs.python3.withPackages (ps: with ps; [ httpx selectolax websockets vncdotool pillow mcp fastapi uvicorn pytest ])) pkgs.ruff ];
        };
      });
    };
}
