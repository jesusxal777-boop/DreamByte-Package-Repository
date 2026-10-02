# DreamByte Package Repository

Repositorio oficial de paquetes para **DreamByte Terminal** y **DreamByte OS**.

Es un repositorio **estático**: DreamByte Terminal solo necesita descargar archivos por HTTPS (`pkg update`, `pkg search`, `pkg info`, `pkg install`...). No hay servidor.

## Estructura

```
repository.json              índice principal (generado, no editar a mano)
packages/<nombre>/package.json   manifest de cada paquete
tools/generate_repository.py     valida los manifests y regenera el índice
docs/package-format.md       formato de package.json
docs/repository-api.md       protocolo que debe seguir el cliente (pkg)
.github/workflows/validate-repository.yml   validación automática
```

## Paquetes actuales

| Paquete | Tipo | Estado |
|---|---|---|
| `wget` | cli | `planned` (aún no hay archivo descargable) |
| `python` | runtime | `planned` (requiere un runtime real para Android) |

Un paquete `planned` o `metadata-only` aparece en búsquedas e info, pero **no se puede instalar** todavía.

## Cómo descubre paquetes el cliente

1. `GET {base_url}repository.json` → lista de paquetes con nombre, versión, descripción, tipo, estado, arquitecturas y dependencias.
2. `GET {base_url}` + `manifest` → el `package.json` completo, con `download.url` y `download.sha256`.
3. Descargar el archivo, calcular su SHA-256 y compararlo con `download.sha256`. Si no coincide, se rechaza.

El detalle de cada comando está en [`docs/repository-api.md`](docs/repository-api.md).

## Validar el repositorio

Solo hace falta Python 3 (sin dependencias):

```bash
python tools/generate_repository.py --check
```

Comprueba JSON válido, campos obligatorios, nombres, versiones semver, arquitecturas, duplicados, dependencias (que existan, que cumplan la versión y sin ciclos), URLs HTTPS, formato de SHA-256 y que `repository.json` coincida con los manifests. Los errores indican el archivo y el campo exactos:

```
ERROR packages/wget/package.json [version]: must be a semantic version MAJOR.MINOR.PATCH, got '1.x'
```

GitHub Actions ejecuta esto en cada `push` y `pull_request`.

## Añadir un paquete nuevo

1. Crea `packages/<nombre>/package.json` (formato en [`docs/package-format.md`](docs/package-format.md)).
2. Si todavía no existe el archivo real, usa `"status": "planned"` (o `"metadata-only"`) y no pongas `download`. **No inventes URLs ni hashes.**
3. Regenera el índice:
   ```bash
   python tools/generate_repository.py
   ```
4. Comprueba y haz commit de `packages/<nombre>/` **y** `repository.json`:
   ```bash
   python tools/generate_repository.py --check
   ```

Para pasar un paquete a `stable`: sube el artefacto real a una URL HTTPS, calcula su SHA-256 (`sha256sum archivo`), añade `download` y cambia `status`.

## Qué falta

- Implementar `pkg` en DreamByte Terminal (cliente HTTP, cache del índice, estado de instalados).
- Un runtime de Python real compatible con Android, y su artefacto + SHA-256.
- Artefactos reales de `wget`.
- Backend privilegiado para los paquetes `scope: "system"` de DreamByte OS M.
- Firma de manifests (mejora futura).
