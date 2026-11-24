"""Windows에서 더블클릭으로 통합 검색 에이전트 실습 화면을 연다."""

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import urlopen

from chatbot import PDF_FILE, ROOT, SOURCES, ask


HOST = "127.0.0.1"
PORT = 8768
APP_ID = "integrated-search-agent"


class AppServer(ThreadingHTTPServer):
    allow_reuse_address = False

    @property
    def origin(self):
        return f"http://{HOST}:{self.server_port}"


class AppHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send_bytes(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_bytes(body, "application/json; charset=utf-8", status)

    def do_GET(self):
        if self.path == "/":
            self.send_bytes((ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/manual.pdf":
            self.send_bytes(PDF_FILE.read_bytes(), "application/pdf")
        elif self.path == "/api/status":
            self.send_json({"app": APP_ID})
        elif self.path == "/favicon.ico":
            self.send_bytes(b"", "image/x-icon", 204)
        else:
            self.send_json({"error": "페이지를 찾을 수 없습니다."}, 404)

    def do_POST(self):
        if self.headers.get("Origin") != self.server.origin:
            self.send_json({"error": "챗봇 화면에서 요청해 주세요."}, 403)
            return
        if self.path == "/api/close":
            self.send_json({"closed": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.path != "/api/ask":
            self.send_json({"error": "페이지를 찾을 수 없습니다."}, 404)
            return

        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 8192:
                raise ValueError
            request = json.loads(self.rfile.read(size))
            question = request.get("question") if isinstance(request, dict) else None
            if not isinstance(question, str) or not 0 < len(question.strip()) <= 500:
                raise ValueError
            sources = request.get("sources")
            if not isinstance(sources, list) or not sources or not set(sources) <= set(SOURCES):
                raise ValueError
        except ValueError:
            self.send_json({"error": "질문을 1~500자로 입력하고 사용할 자료를 하나 이상 골라 주세요."}, 400)
            return

        try:
            out = ask(question.strip(), sources)
        except RuntimeError as error:
            self.send_json({"error": str(error)}, 502)
        except OSError:
            self.send_json({"error": "자료 파일을 읽을 수 없습니다."}, 500)
        else:
            self.send_json(out)


def main():
    try:
        server = AppServer((HOST, PORT), AppHandler)
    except OSError:
        existing_origin = f"http://{HOST}:{PORT}"
        try:
            with urlopen(f"{existing_origin}/api/status", timeout=1) as response:
                if json.load(response) == {"app": APP_ID}:
                    webbrowser.open(existing_origin)
                    return
        except (URLError, OSError, ValueError):
            pass
        server = AppServer((HOST, 0), AppHandler)

    with server:
        webbrowser.open(server.origin)
        server.serve_forever()


if __name__ == "__main__":
    main()
