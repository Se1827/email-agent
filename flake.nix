{
  description = "Intelligent Email Agent - Development Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            python
            pkgs.docker
            pkgs.python312Packages.pip
            pkgs.python312Packages.virtualenv
            pkgs.nodejs_22

            # System libs that some Python packages need
            pkgs.stdenv.cc.cc.lib
            pkgs.zlib
            pkgs.openssl
          ];

          shellHook = ''
            echo "Email Agent dev shell"

            if [ ! -d .venv ]; then
              echo "Creating Python virtual environment..."
              python -m venv .venv
            fi

            source .venv/bin/activate
            export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath [
              pkgs.stdenv.cc.cc.lib
              pkgs.zlib
              pkgs.openssl
            ]}:$LD_LIBRARY_PATH"
          '';
        };
      }
    );
}
