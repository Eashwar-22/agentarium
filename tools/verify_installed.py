"""Run with the wheel-installed interpreter from outside the source checkout."""
import asyncio
import subprocess
import sys
import sysconfig
from pathlib import Path

import agentarium
from agentarium.dashboard import create_app


def main():
    location=Path(agentarium.__file__).resolve()
    installed_root=Path(sysconfig.get_path('purelib')).resolve()
    assert location.is_relative_to(installed_root), f'Source checkout imported instead of installed wheel: {location}'
    app=create_app()
    for target in ('/','/styles.css','/run_view.js','/script.js'):
        route=next(route for route in app.routes if route.path==target)
        response=asyncio.run(route.endpoint())
        assert Path(response.path).is_file(), target
    executable=Path(sysconfig.get_path('scripts'))/('agentarium-dashboard.exe' if sys.platform=='win32' else 'agentarium-dashboard')
    subprocess.run([str(executable),'--help'],check=True,capture_output=True)
    subprocess.run([sys.executable,'-m','pip','check'],check=True)
    print('Installed wheel import, packaged frontend assets, CLI, and dependencies: PASS')

if __name__=='__main__':main()
