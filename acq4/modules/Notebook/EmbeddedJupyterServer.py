"""
EmbeddedJupyterServer.py - Jupyter server running in ACQ4 process with ACQ4 memory access

This module runs a Jupyter Notebook server in a background thread within the ACQ4 process.
Kernels created by this server have direct access to ACQ4's Manager, devices, and live data.
"""

import os
import sys
import threading
import time
import socket
from contextlib import closing

import numpy as np
import pyqtgraph as pg

from jupyter_server.serverapp import ServerApp
from jupyter_server.services.kernels.kernelmanager import MappingKernelManager
from ipykernel.kernelapp import IPKernelApp
from traitlets import default


class ACQ4KernelManager(MappingKernelManager):
    """Custom kernel manager that injects ACQ4 namespace into all kernels."""

    def __init__(self, acq4_manager=None, **kwargs):
        super().__init__(**kwargs)
        self.acq4_manager = acq4_manager

    def start_kernel(self, kernel_id=None, path=None, **kwargs):
        """Start a kernel and inject ACQ4 namespace."""
        kernel_id = super().start_kernel(kernel_id=kernel_id, path=path, **kwargs)

        # Get the kernel and inject ACQ4 namespace
        if self.acq4_manager is not None:
            try:
                kernel = self.get_kernel(kernel_id)
                km = kernel.kernel_manager

                # Wait for kernel to be ready
                for _ in range(50):  # 5 second timeout
                    if km.is_alive():
                        break
                    time.sleep(0.1)

                # Inject ACQ4 namespace through kernel's shell
                if hasattr(km, 'kernel'):
                    km.kernel.shell.push({
                        'man': self.acq4_manager,
                        'manager': self.acq4_manager,
                        'pg': pg,
                        'np': np,
                        'Qt': __import__('acq4.util.Qt', fromlist=['Qt']).Qt,
                    })
                    print(f"✓ Injected ACQ4 namespace into kernel {kernel_id}")
            except Exception as e:
                print(f"Warning: Could not inject ACQ4 namespace into kernel: {e}")

        return kernel_id


class ACQ4ServerApp(ServerApp):
    """Custom Jupyter server configured for ACQ4 integration."""

    @default('kernel_manager_class')
    def _default_kernel_manager_class(self):
        return ACQ4KernelManager


class EmbeddedJupyterServer:
    """Manages an embedded Jupyter server running in ACQ4."""

    def __init__(self, acq4_manager, port=None, notebook_dir=None):
        """Initialize the embedded Jupyter server.

        Parameters
        ----------
        acq4_manager : Manager
            The ACQ4 Manager instance to inject into kernels
        port : int, optional
            Port to run server on (auto-selected if None)
        notebook_dir : str, optional
            Root directory for notebooks (defaults to cwd)
        """
        self.acq4_manager = acq4_manager
        self.port = port or self._find_free_port()
        self.notebook_dir = notebook_dir or os.getcwd()
        self.server_thread = None
        self.server_app = None
        self.running = False

    def _find_free_port(self):
        """Find an available port."""
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(('', 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]

    def start(self):
        """Start the Jupyter server in a background thread."""
        if self.running:
            print("Server already running")
            return

        def run_server():
            try:
                # Create server app
                self.server_app = ACQ4ServerApp()

                # Configure server
                self.server_app.ip = '127.0.0.1'
                self.server_app.port = self.port
                self.server_app.open_browser = False
                self.server_app.notebook_dir = self.notebook_dir
                self.server_app.token = ''  # No authentication for local server
                self.server_app.password = ''
                self.server_app.disable_check_xsrf = True

                # Set custom kernel manager with ACQ4 access
                self.server_app.kernel_manager_class = ACQ4KernelManager

                # Initialize the app
                self.server_app.initialize(argv=[])

                # Inject ACQ4 manager into kernel manager
                if hasattr(self.server_app, 'kernel_manager'):
                    self.server_app.kernel_manager.acq4_manager = self.acq4_manager

                print(f"✓ Jupyter server starting on http://127.0.0.1:{self.port}")
                self.running = True

                # Start the server (blocks)
                self.server_app.start()

            except Exception as e:
                print(f"Error starting Jupyter server: {e}")
                import traceback
                traceback.print_exc()
                self.running = False

        # Start server in background thread
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

        # Wait for server to be ready
        for _ in range(100):  # 10 second timeout
            try:
                import urllib.request
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}", timeout=0.5):
                    break
            except:
                time.sleep(0.1)
        else:
            print("Warning: Server may not be ready yet")

    def stop(self):
        """Stop the Jupyter server."""
        if self.server_app:
            try:
                self.server_app.stop()
                self.running = False
                print("✓ Jupyter server stopped")
            except Exception as e:
                print(f"Error stopping server: {e}")

    def get_notebook_url(self, notebook_path):
        """Get the URL to open a specific notebook.

        Parameters
        ----------
        notebook_path : str
            Absolute path to the notebook file

        Returns
        -------
        str
            URL to open the notebook in the embedded server
        """
        # Make path relative to notebook_dir
        rel_path = os.path.relpath(notebook_path, self.notebook_dir)
        # URL encode the path
        from urllib.parse import quote
        encoded_path = quote(rel_path)
        return f"http://127.0.0.1:{self.port}/notebooks/{encoded_path}"

    def get_tree_url(self, directory=None):
        """Get the URL to the file browser.

        Parameters
        ----------
        directory : str, optional
            Directory to show (relative to notebook_dir)

        Returns
        -------
        str
            URL to the file browser
        """
        if directory:
            from urllib.parse import quote
            rel_path = os.path.relpath(directory, self.notebook_dir)
            encoded_path = quote(rel_path)
            return f"http://127.0.0.1:{self.port}/tree/{encoded_path}"
        return f"http://127.0.0.1:{self.port}/tree"
