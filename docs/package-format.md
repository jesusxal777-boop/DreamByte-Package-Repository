# Formato de paquete (`package.json`)

Cada paquete vive en `packages/<nombre>/package.json`. El nombre de la carpeta **debe ser igual** al campo `name`.

## Campos

| Campo | Obligatorio | Descripción |
|---|---|---|
| `name` | sí | Identificador. Regex `^[a-z0-9][a-z0-9._+-]{0,63}$`. Igual al nombre de la carpeta. |
| `version` | sí | Versión semántica `MAJOR.MINOR.PATCH` (admite `-prerelease`). Usa `0.0.0` mientras el paquete solo esté planificado. |
| `description` | sí | Texto corto. |
| `maintainer` | sí | Quién lo mantiene. |
| `license` | sí | Identificador SPDX (`MIT`, `GPL-3.0-or-later`...). `NOASSERTION` si aún no está decidida. |
| `architecture` | sí | Lista de: `arm64-v8a`, `armeabi-v7a`, `x86_64`, `x86`, `all`. `all` va sola (paquetes sin binarios nativos, p. ej. scripts). |
| `dependencies` | sí | Lista de strings: `"nombre"` o `"nombre>=1.0.0"`. Operadores: `>=  <=  >  <  =`. Puede ser `[]`. |
| `type` | sí | Categoría, ver abajo. |
| `status` | sí | Estado, ver abajo. |
| `download` | según `status` | Dónde está el archivo y su SHA-256. Ver abajo. |
| `scope` | no | `user` (por defecto) o `system`. Ver "Alcance". |
| `homepage` | no | URL HTTPS. |

Los campos desconocidos generan un aviso (no un error) para poder ampliar el formato.

## `type`

| Valor | Para |
|---|---|
| `app` | Aplicaciones |
| `cli` | Comandos de terminal |
| `library` | Bibliotecas |
| `runtime` | Runtimes / lenguajes (p. ej. Python) |
| `tool` | Herramientas |
| `script` | Scripts |
| `resource` | Recursos (fuentes, datos, temas...) |
| `os-m` | Paquetes específicos de DreamByte OS M |

`type` describe **qué es** el paquete. El formato del archivo descargable se indica en `download.format`.

## `status`

| Valor | ¿Instalable? | `download` |
|---|---|---|
| `stable` | sí | obligatorio |
| `beta` | sí | obligatorio |
| `deprecated` | sí (con aviso) | obligatorio |
| `planned` | **no** | opcional |
| `metadata-only` | **no** | opcional |

`planned` y `metadata-only` aparecen en `pkg search`, `pkg list` y `pkg info`, pero `pkg install` debe rechazarlos. Un paquete `stable`/`beta` no puede depender de uno `planned`/`metadata-only`.

## `download`

Hay dos formas. Si está presente, siempre se valida (HTTPS + SHA-256 válido).

**Artefacto único** (para `architecture: ["all"]` o un mismo archivo para todas las arquitecturas):

```json
"download": {
  "url": "<URL HTTPS real del archivo>",
  "sha256": "<64 caracteres hexadecimales en minúscula>",
  "size": 123456,
  "format": "tar.gz"
}
```

**Un artefacto por arquitectura** (lo habitual para binarios nativos):

```json
"download": {
  "arm64-v8a": { "url": "<...>", "sha256": "<...>" },
  "x86_64":    { "url": "<...>", "sha256": "<...>" }
}
```

En paquetes instalables, debe haber una entrada por cada arquitectura declarada en `architecture`.

`size` (bytes) y `format` (`tar.gz`, `tar.xz`, `zip`, `bin`, `apk`, `script`) son opcionales.

> Los valores entre `<...>` son marcadores. **No pongas URLs ni hashes que no correspondan a un archivo real.** Mientras no exista el artefacto, deja el paquete como `planned` o `metadata-only` y omite `download`.

## Dependencias

```json
"dependencies": ["openssl>=3.0.0", "ca-certificates"]
```

- Cada dependencia debe existir en `packages/`.
- Si lleva restricción, la versión actual del paquete dependido debe cumplirla.
- No se permiten auto-dependencias ni ciclos.

## Alcance (`scope`)

- `user`: se instala dentro del almacenamiento privado de la app (sandbox de Android). Es lo único que puede instalar DreamByte Terminal en Android normal.
- `system`: reservado para DreamByte OS M, que tendrá un backend con privilegios separado. Un cliente sin ese backend **debe rechazar** estos paquetes.

## Artefacto físico

Cuando un paquete es `beta`, `stable` o `deprecated`, `download` debe apuntar a un `.dbpkg` real. El formato físico y sus reglas de extracción segura están documentados en [`dbpkg-format.md`](dbpkg-format.md). Para construir y comprobar un paquete usa `tools/build_package.py` y `tools/validate_package.py`; el hash de `download` debe ser el SHA-256 del archivo final publicado.

## Ejemplo (paquete planificado, tal como existe hoy)

```json
{
  "name": "wget",
  "version": "0.0.0",
  "description": "Network downloader for DreamByte Terminal",
  "maintainer": "DreamByte Studios",
  "license": "NOASSERTION",
  "architecture": ["arm64-v8a", "armeabi-v7a", "x86_64"],
  "dependencies": [],
  "type": "cli",
  "status": "planned"
}
```
