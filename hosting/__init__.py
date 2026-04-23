"""Local hosting - web server, domains, SSL, reverse proxy on local hardware."""
import os, socket, ssl, threading, time, json, hashlib, subprocess, mimetypes
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

class LocalHost:
    def __init__(self, root_dir=None, port=8080):
        self.root_dir = root_dir or os.path.expanduser("~/Sentience/sites")
        self.port = port
        self.sites = {}
        self.running = False
        self.thread = None
        self.proxy_rules = {}
        self.ssl_certs = {}

    def create_site(self, name, domain=None, port=None):
        site_dir = Path(self.root_dir) / name
        site_dir.mkdir(parents=True, exist_ok=True)
        p = port or (5000 + len(self.sites))
        self.sites[name] = {"name": name, "domain": domain or f"{name}.local", "dir": str(site_dir), "port": p, "routes": [], "active": True, "index_files": ["index.html", "index.htm"]}
        self.start_site(name)
        return {"site": name, "url": f"http://localhost:{p}", "dir": str(site_dir)}

    def start_site(self, name):
        if name not in self.sites: return {"error": "site not found"}
        s = self.sites[name]
        site_dir = s["dir"]
        port = s["port"]
        def run():
            class Handler(SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=site_dir, **kwargs)
                def do_GET(self):
                    if self.path == "/health":
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "ok", "site": name}).encode())
                        return
                    super().do_GET()
                def log_message(self, fmt, *args): pass
            HTTPServer(("0.0.0.0", port), Handler).serve_forever()
        t = threading.Thread(target=run, daemon=True)
        t.start()
        s["running"] = True
        return {"status": "started", "port": port}

    def add_route(self, site_name, path, route_type, code=None, proxy_to=None):
        if site_name not in self.sites: return {"error": "site not found"}
        self.sites[site_name]["routes"].append({"path": path, "type": route_type, "code": code, "proxy_to": proxy_to})
        return {"site": site_name, "route": path}

    def add_ssl(self, site_name, cert_file=None, key_file=None):
        if site_name not in self.sites: return {"error": "site not found"}
        self.sites[site_name]["ssl"] = {"cert": cert_file, "key": key_file}
        return {"site": site_name, "ssl": True}

    def list_sites(self):
        return [{"name": s["name"], "domain": s["domain"], "port": s["port"], "running": s.get("running", False), "routes": len(s["routes"])} for s in self.sites.values()]

    def delete_site(self, name):
        if name in self.sites: del self.sites[name]
        return {"deleted": name}

    def get_public_url(self, site_name):
        if site_name not in self.sites: return None
        s = self.sites[site_name]
        # Try to get LAN IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return f"http://{ip}:{s['port']}"
        except:
            return f"http://localhost:{s['port']}"

class ReverseProxy:
    def __init__(self, port=80):
        self.port = port
        self.rules = []
        self.running = False

    def add_rule(self, domain, target_host, target_port, ssl=False):
        self.rules.append({"domain": domain, "target_host": target_host, "target_port": target_port, "ssl": ssl})

    def start(self):
        self.running = True
        t = threading.Thread(target=self._serve, daemon=True)
        t.start()

    def _serve(self):
        import socket as s
        server = s.socket(s.AF_INET, s.SOCK_STREAM)
        server.setsockopt(s.SOL_SOCKET, s.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", self.port))
        server.listen(50)
        while self.running:
            conn, addr = server.accept()
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        try:
            data = conn.recv(4096)
            host = None
            for rule in self.rules:
                if rule["domain"] in data.decode("utf-8", errors="ignore"):
                    host = rule["target_host"]
                    port = rule["target_port"]
                    break
            if host:
                remote = socket.socket()
                remote.connect((host, port))
                remote.sendall(data)
                response = remote.recv(8192)
                conn.sendall(response)
                remote.close()
            conn.close()
        except: pass

# Global instances
_local_host = LocalHost()
_proxy = ReverseProxy()

def get_host(): return _local_host
def get_proxy(): return _proxy
