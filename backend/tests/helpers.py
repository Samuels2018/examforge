from fastapi.testclient import TestClient

MATERIAL_TEXT = """El modelo TCP/IP divide la comunicación en cuatro capas: acceso a la red,
internet, transporte y aplicación. La capa de transporte usa TCP para ofrecer entrega fiable y
UDP para baja latencia. TCP realiza el saludo de tres vías para establecer una conexión confiable
entre dos hosts. El protocolo IP se encarga del direccionamiento lógico y del enrutamiento de
paquetes entre redes. El DNS traduce nombres de dominio legibles en direcciones IP numéricas.
HTTP es un protocolo de aplicación sin estado que se apoya en TCP para transportar peticiones y
respuestas. Un cortafuegos filtra tráfico según reglas de puertos, direcciones y protocolos.
La NAT permite que varios dispositivos compartan una única dirección IP pública. El enrutamiento
dinámico actualiza las tablas de rutas cuando cambia la topología de la red. La conmutación
ethernet aprende direcciones MAC y reenvía tramas solo por el puerto necesario. Una VLAN separa
dominios de broadcast dentro de la misma infraestructura física. El protocolo ARP resuelve
direcciones IP locales en direcciones MAC. DHCP asigna automáticamente configuración de red a
los clientes. TLS cifra la comunicación entre cliente y servidor y garantiza su autenticidad.
Un proxy inverso distribuye peticiones entre varios servidores de aplicación. La redundancia de
enlaces evita un único punto de fallo en la red. El monitoreo de latencia y pérdida de paquetes
permite detectar degradaciones antes de que afecten a los usuarios."""


def create_workspace(client: TestClient, name: str = "Examen de redes") -> str:
    response = client.post(
        "/api/workspaces",
        json={"name": name, "description": "Prueba de integración"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def upload_material(
    client: TestClient,
    workspace_id: str,
    *,
    text: str = MATERIAL_TEXT,
    filename: str = "redes.txt",
) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/materials",
        files=[("files", (filename, text.encode("utf-8"), "text/plain"))],
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


def generate_exercises(
    client: TestClient,
    workspace_id: str,
    **overrides,
) -> dict:
    payload = {
        "count": 6,
        "difficulties": ["basic", "intermediate", "advanced"],
        "focus": "TCP",
    }
    payload.update(overrides)
    response = client.post(f"/api/workspaces/{workspace_id}/exercises/generate", json=payload)
    assert response.status_code == 201, response.text
    return response.json()
