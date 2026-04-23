"""Remote computer control - SSH, SFTP, remote execution."""
import paramiko, socket, time, os
from pathlib import Path

class RemoteComputer:
    def __init__(self, host, port=22, username=None, password=None, key_path=None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self.client = None
        self.sftp = None

    def connect(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if self.key_path:
                self.client.connect(self.host, port=self.port, username=self.username, key_filename=self.key_path)
            else:
                self.client.connect(self.host, port=self.port, username=self.username, password=self.password, timeout=10)
            self.sftp = self.client.open_sftp()
            return {"status": "connected", "host": self.host}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run(self, command):
        if not self.client: return {"error": "not connected"}
        stdin, stdout, stderr = self.client.exec_command(command, get_pty=True)
        return {
            "stdout": stdout.read().decode(),
            "stderr": stderr.read().decode(),
            "exit_code": stdout.channel.recv_exit_status()
        }

    def upload_file(self, local_path, remote_path):
        if not self.sftp: return {"error": "not connected"}
        self.sftp.put(local_path, remote_path)
        return {"status": "uploaded", "remote": remote_path}

    def download_file(self, remote_path, local_path):
        if not self.sftp: return {"error": "not connected"}
        self.sftp.get(remote_path, local_path)
        return {"status": "downloaded", "local": local_path}

    def list_dir(self, path="."):
        return {"files": self.sftp.listdir(path)} if self.sftp else {"error": "not connected"}

    def disconnect(self):
        if self.sftp: self.sftp.close()
        if self.client: self.client.close()
        return {"status": "disconnected"}

    def execute_tool(self, tool_name, args, context):
        return {"tool": tool_name, "args": args, "result": self.run(args.get("command", "echo done"))}
__all__ = ["RemoteComputer"]
