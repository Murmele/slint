# Debug considerations

Enable slint_debug_property configuration:
    - export RUSTFLAGS="--cfg slint_debug_property"

VSCode Launch example:
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "type": "lldb",
            "request": "launch",
            "name": "Debug executable 'slint-viewer'",
            "cargo": {
                "args": [
                    "build",
                    "--bin=slint-viewer",
                    "--package=slint-viewer"
                ],
                "filter": {
                    "name": "slint-viewer",
                    "kind": "bin"
                }
            },
            "env": {
				"RUSTFLAGS": "--cfg slint_debug_property"
			},
            "args": ["<Path to slint file>"],
            "cwd": "${workspaceFolder}"
        },
    ]
}
```