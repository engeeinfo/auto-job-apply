import socket
import threading
import time
import urllib.request
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def run_devtools_proxy():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(('127.0.0.1', 9889))
        server.listen(5)
        print("Proxy started on 9889")
    except Exception as e:
        print(f"Proxy failed to start: {e}")
        return

    def handle_client(client_sock):
        try:
            data = client_sock.recv(4096)
            if not data:
                client_sock.close()
                return

            if b"GET /json/version" in data:
                try:
                    with urllib.request.urlopen("http://127.0.0.1:9888/json/version") as response:
                        res_data = response.read().decode('utf-8')
                    parsed = json.loads(res_data)
                    
                    # Override Browser and User-Agent to match ChromeDriver version 148
                    parsed["Browser"] = "Chrome/148.0.6613.120"
                    if "User-Agent" in parsed:
                        parsed["User-Agent"] = parsed["User-Agent"].replace("140.0.0.0", "148.0.6613.120")
                    
                    print(f"Proxy: Overriding Browser to {parsed['Browser']}")
                    print(f"Proxy: Overriding User-Agent to {parsed['User-Agent']}")
                    
                    if "webSocketDebuggerUrl" in parsed:
                        parsed["webSocketDebuggerUrl"] = parsed["webSocketDebuggerUrl"].replace("9888", "9889")
                    
                    body = json.dumps(parsed).encode('utf-8')
                    http_response = (
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: application/json; charset=UTF-8\r\n"
                        b"Content-Length: " + str(len(body)).encode('ascii') + b"\r\n"
                        b"Connection: close\r\n\r\n" + body
                    )
                    client_sock.sendall(http_response)
                except Exception as ex:
                    print("Proxy error modifying /json/version:", ex)
                client_sock.close()
                return

            # Tunnel all other traffic
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.connect(('127.0.0.1', 9888))
            target_sock.sendall(data)

            def forward(src, dst):
                try:
                    while True:
                        buf = src.recv(4096)
                        if not buf:
                            break
                        dst.sendall(buf)
                except Exception:
                    pass
                finally:
                    src.close()
                    dst.close()

            threading.Thread(target=forward, args=(client_sock, target_sock), daemon=True).start()
            threading.Thread(target=forward, args=(target_sock, client_sock), daemon=True).start()

        except Exception as e:
            try:
                client_sock.close()
            except Exception:
                pass

    while True:
        try:
            sock, _ = server.accept()
            threading.Thread(target=handle_client, args=(sock,), daemon=True).start()
        except Exception:
            break

# Start proxy thread
proxy_thread = threading.Thread(target=run_devtools_proxy, daemon=True)
proxy_thread.start()

time.sleep(1)

# Check if embedded port 9888 is active
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1.0)
embedded_active = s.connect_ex(('127.0.0.1', 9888)) == 0
s.close()

if embedded_active:
    try:
        print("Connecting to proxy port 9889...")
        options = Options()
        options.add_experimental_option("debuggerAddress", "127.0.0.1:9889")
        driver = webdriver.Chrome(options=options)
        print("SUCCESS! Connected to embedded browser via proxy!")
        print("Current browser title:", driver.title)
        driver.quit()
    except Exception as e:
        print("Connection failed:")
        import traceback
        traceback.print_exc()
else:
    print("Embedded browser is not running on port 9888. Please start the main application first.")
