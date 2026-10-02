# Protocolo del repositorio

El repositorio es **estático**: solo archivos servidos por HTTPS. No hay servidor ni API dinámica. DreamByte Terminal solo necesita un cliente HTTP.

## Archivos que consume el cliente

Todo cuelga de `base_url` (campo de `repository.json`), que hoy es
`https://raw.githubusercontent.com/jesusxal777-boop/DreamByte-Package-Repository/main/`.

| Qué | URL |
|---|---|
| Índice | `{base_url}repository.json` |
| Manifest de un paquete | `{base_url}` + `packages[i].manifest` |
| Artefacto | `download.url` del manifest (puede estar en otro host, siempre HTTPS) |

## `repository.json`

```json
{
  "format_version": 1,
  "name": "DreamByte Official Package Repository",
  "repository_version": 1,
  "base_url": "https://raw.githubusercontent.com/.../main/",
  "updated_at": "2026-10-02T06:10:00Z",
  "package_count": 2,
  "packages": [
    {
      "name": "wget",
      "version": "0.0.0",
      "description": "Network downloader for DreamByte Terminal",
      "type": "cli",
      "status": "planned",
      "architecture": ["arm64-v8a", "armeabi-v7a", "x86_64"],
      "dependencies": [],
      "manifest": "packages/wget/package.json",
      "manifest_sha256": "<sha256 del package.json>"
    }
  ]
}
```

- `format_version`: versión del **formato**. Si el cliente no la entiende, debe avisar y no continuar.
- `repository_version`: entero que sube cada vez que cambia el contenido del repositorio. Sirve para saber si hay algo nuevo.
- `updated_at`: UTC, ISO 8601.
- Cada entrada del índice trae lo suficiente para `search`, `list` e `info` básico **sin descargar más archivos**. La URL y el SHA-256 del artefacto solo están en el manifest.
- `manifest_sha256` permite comprobar que el manifest descargado es el que el índice anuncia.

El índice lo genera `tools/generate_repository.py`. No se edita a mano.

## Comandos de `pkg` y qué hace cada uno

### `pkg update`
1. `GET {base_url}repository.json`.
2. Comprobar `format_version` soportado.
3. Guardarlo en local (cache). Si `repository_version` es igual al guardado, no hay cambios.

### `pkg search <texto>` / `pkg list`
Trabajan **solo con el índice local**. `search` filtra por `name` y `description`; `list` muestra todo. Mostrar `status` para que se vean los `planned`.

### `pkg info <paquete>`
Mostrar los datos del índice. Si hace falta el detalle (licencia, `download`, `scope`), descargar el manifest y verificar su `manifest_sha256`.

### `pkg install <paquete>`
1. Buscar el paquete en el índice. Si no existe: error.
2. Descargar el manifest y verificar `manifest_sha256`.
3. Rechazar si `status` es `planned` o `metadata-only` ("todavía no tiene archivo instalable").
4. Rechazar si `scope` es `system` y no hay backend privilegiado.
5. **Compatibilidad de arquitectura** (ver abajo).
6. **Resolver dependencias** (ver abajo).
7. Para cada paquete a instalar, en orden de dependencias:
   1. Descargar `download.url` (solo HTTPS) a un archivo temporal.
   2. Calcular SHA-256 mientras se descarga.
   3. Comparar con `download.sha256`.
   4. **Si no coincide: borrar el temporal, abortar, no instalar nada.**
   5. Extraer dentro del directorio privado de la app, rechazando rutas absolutas o con `..`.
   6. Registrar `nombre` y `versión` en el estado local de instalados.

### `pkg remove <paquete>`
Borrar los archivos que ese paquete instaló y quitarlo del estado local. Si otro paquete instalado depende de él, avisar o negarse.

### `pkg upgrade`
Para cada paquete instalado, comparar su versión con la del índice (comparación semver). Si el del índice es mayor, instalar con el mismo flujo que `pkg install`.

## Arquitectura

1. El dispositivo declara sus ABI en orden de preferencia (en Android, `Build.SUPPORTED_ABIS`).
2. Un paquete es compatible si `architecture` contiene `all` o alguna ABI del dispositivo.
3. Se usa la primera ABI del dispositivo que el paquete soporte.
4. Si `download` es un mapa por arquitectura, se toma la entrada de esa ABI. Si es un artefacto único, se usa tal cual.
5. Sin ABI compatible: error claro, sin descargar nada.

## Dependencias

Algoritmo sencillo (sin solver complejo, a propósito):

```
resolver(paquete):
    para cada dep "nombre[op version]" del manifest:
        buscar "nombre" en el índice            -> si no existe: error
        comprobar la restricción contra su versión del índice -> si no cumple: error
        si ya está instalado y cumple: saltar
        resolver(dep)
    añadir paquete al plan (después de sus dependencias)
```

Debe llevar un conjunto de "en curso" para detectar ciclos (el validador ya los prohíbe en el repositorio, pero el cliente debe protegerse igualmente). El plan resultante es el orden de instalación. Mostrar el plan al usuario antes de descargar.

## Verificación SHA-256 (ejemplo en Kotlin)

```kotlin
fun sha256Hex(file: File): String {
    val md = java.security.MessageDigest.getInstance("SHA-256")
    file.inputStream().use { input ->
        val buf = ByteArray(64 * 1024)
        while (true) {
            val n = input.read(buf)
            if (n < 0) break
            md.update(buf, 0, n)
        }
    }
    return md.digest().joinToString("") { "%02x".format(it) }
}

// val ok = sha256Hex(tmp).equals(expected, ignoreCase = true)
// if (!ok) { tmp.delete(); error("SHA-256 mismatch for $name") }
```

## Reglas de seguridad para los clientes

- Solo HTTPS. Rechazar redirecciones a HTTP.
- Nunca ejecutar ni extraer un archivo cuyo hash no coincida.
- Instalar únicamente dentro del almacenamiento privado de la app. Un cliente en Android normal respeta el sandbox del sistema: sin root, sin modificar archivos del sistema.
- Los paquetes `scope: "system"` son solo para DreamByte OS M con backend privilegiado.
- Tratar todo el contenido descargado como no confiable hasta verificar el SHA-256.

Esto protege contra descargas corruptas y contra alteraciones del archivo, pero **no** contra un manifest malicioso publicado en este mismo repositorio. La firma de manifests queda como mejora futura.

## Estado local sugerido (lo gestiona el cliente, no este repositorio)

```json
{ "installed": { "wget": { "version": "1.0.0", "installed_at": "..." } } }
```
