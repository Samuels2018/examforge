import { expect, test } from "@playwright/test";

const MATERIAL = `El modelo TCP/IP divide la comunicación en cuatro capas: acceso a la red,
internet, transporte y aplicación. La capa de transporte usa TCP para ofrecer entrega fiable y
UDP para baja latencia. TCP realiza el saludo de tres vías para establecer una conexión confiable
entre dos hosts. El protocolo IP se encarga del direccionamiento lógico y del enrutamiento de
paquetes entre redes. El DNS traduce nombres de dominio legibles en direcciones IP numéricas.
HTTP es un protocolo de aplicación sin estado que se apoya en TCP para transportar peticiones y
respuestas. Un cortafuegos filtra tráfico según reglas de puertos, direcciones y protocolos.
La NAT permite que varios dispositivos compartan una única dirección IP pública.
El enrutamiento dinámico actualiza las tablas de rutas cuando cambia la topología de la red.
La conmutación ethernet aprende direcciones MAC y reenvía tramas solo por el puerto necesario.
Una VLAN separa dominios de broadcast dentro de la misma infraestructura física.
El protocolo ARP resuelve direcciones IP locales en direcciones MAC.`;

test("crear evaluación, subir material, generar y corregir un ejercicio", async ({ page }) => {
  const workspaceName = `E2E ${Date.now()}`;

  await page.goto("/");
  await page.getByRole("button", { name: "Nueva evaluación" }).click();
  await page.getByLabel("Nombre").fill(workspaceName);
  await page.getByRole("button", { name: "Crear", exact: true }).click();

  await expect(page.getByRole("heading", { name: workspaceName })).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: "redes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(MATERIAL, "utf-8"),
  });
  await expect(page.getByText("redes.txt")).toBeVisible();
  await expect(page.getByText(/procesados y listos/i)).toBeVisible({ timeout: 20_000 });

  await page.getByRole("tab", { name: /Ejercicios/ }).click();
  await page.locator('input[type="number"]').fill("3");
  await page.getByRole("button", { name: /Generar 3 ejercicios/ }).click();
  await expect(page.getByText(/ejercicios nuevos/)).toBeVisible({ timeout: 30_000 });

  const firstOption = page.locator(".option-button").first();
  if (await firstOption.count()) {
    await firstOption.click();
  } else {
    await page.getByLabel("Tu respuesta").fill("TCP");
  }
  await page.getByRole("button", { name: "Comprobar respuesta" }).click();
  await expect(page.getByText("Por qué").first()).toBeVisible();

  await page.getByRole("tab", { name: /Progreso/ }).click();
  await expect(page.getByText(/precisión|Precisión/i).first()).toBeVisible();
});
