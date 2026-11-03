#!/usr/bin/env python3
"""Smoke-test the Blender MCP server over stdio JSON-RPC (no MCP client needed).

Usage: python scripts/test-blender-mcp.py [--full]
--full additionally creates a cube scene, exports GLB, validates it and renders a PNG.
"""
import json
import os
import subprocess
import sys
import tempfile

SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "tools", "blender-mcp", "server.py")


def rpc(proc, payload):
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("server closed stdout")
    return json.loads(line)


def main():
    full = "--full" in sys.argv
    proc = subprocess.Popen([sys.executable, SERVER], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    results = {}
    try:
        results["initialize"] = rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                           "params": {"protocolVersion": "2024-11-05",
                                                      "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()
        results["tools"] = rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        results["blender_info"] = rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                             "params": {"name": "blender_info", "arguments": {}}})

        if full:
            tmp = tempfile.mkdtemp(prefix="blender-mcp-test-")
            blend = os.path.join(tmp, "test_cube.blend")
            glb = os.path.join(tmp, "test_cube.glb")
            png = os.path.join(tmp, "test_cube.png")
            create = (
                "import bpy\n"
                "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
                "bpy.ops.mesh.primitive_cube_add(size=2)\n"
                "cube = bpy.context.active_object\n"
                "cube.name = 'MCP_TestCube'\n"
                "mat = bpy.data.materials.new('MCP_TestMat')\n"
                "mat.use_nodes = True\n"
                "cube.data.materials.append(mat)\n"
                "bpy.ops.object.light_add(type='SUN')\n"
                "bpy.ops.object.camera_add(location=(6, -6, 4), rotation=(1.1, 0, 0.8))\n"
                "bpy.context.scene.camera = bpy.context.active_object\n"
                f"bpy.ops.wm.save_as_mainfile(filepath=r'{blend}')\n"
                "__mcp_result = {'created': cube.name, 'blend': bpy.data.filepath}\n"
            )
            results["create"] = rpc(proc, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                           "params": {"name": "run_python", "arguments": {"code": create}}})
            results["inspect"] = rpc(proc, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                                            "params": {"name": "inspect_blend", "arguments": {"blend_file": blend}}})
            results["validate"] = rpc(proc, {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                                             "params": {"name": "validate_asset", "arguments": {"blend_file": blend}}})
            results["export"] = rpc(proc, {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                           "params": {"name": "export_asset",
                                                      "arguments": {"blend_file": blend, "output": glb, "format": "glb"}}})
            results["render"] = rpc(proc, {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                                           "params": {"name": "render_preview",
                                                      "arguments": {"blend_file": blend, "output_png": png,
                                                                    "width": 320, "height": 180}}})
            results["artifacts"] = {"blend": os.path.getsize(blend) if os.path.isfile(blend) else 0,
                                    "glb": os.path.getsize(glb) if os.path.isfile(glb) else 0,
                                    "png": os.path.getsize(png) if os.path.isfile(png) else 0}
    finally:
        proc.terminate()

    print(json.dumps(results, indent=2)[:12000])
    ok = all(not r.get("result", {}).get("isError", False) for k, r in results.items() if isinstance(r, dict) and "result" in r)
    if full:
        ok = ok and all(v > 0 for v in results["artifacts"].values())
    print("\nSMOKE TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
