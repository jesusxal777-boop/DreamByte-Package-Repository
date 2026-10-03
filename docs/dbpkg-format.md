# Formato `.dbpkg`

Un `.dbpkg` es un archivo `tar.gz` reproducible. No es un archivo ficticio ni un wrapper: contiene el ejecutable compilado y un manifiesto interno verificable.

```text
META/manifest.json
bin/<comando>
```

`META/manifest.json` contiene `format: "dbpkg-1"`, nombre, versión, arquitectura y la lista de archivos con sus SHA-256 y modos Unix. La lista excluye deliberadamente al propio manifiesto para evitar un hash autorreferente.

## Reglas del instalador

Un cliente debe rechazar antes de extraer:

- rutas absolutas, rutas con `..`, separadores invertidos y duplicados;
- enlaces simbólicos, hard links y dispositivos;
- manifiesto JSON inválido o formato no soportado;
- cualquier SHA-256 que no coincida;
- arquitectura no soportada;
- paquetes `planned` o `metadata-only`;
- paquetes `scope: system` cuando no existe backend privilegiado.

El constructor `tools/build_package.py` fija timestamps, propietario, modos y orden de entradas para que el mismo código produzca un archivo reproducible. El hash publicado siempre se calcula después de generar el archivo final.

## Pipeline de `hello`

```bash
python tools/build_package.py packages/hello --output-dir dist
python tools/validate_package.py dist/hello-1.0.0-x86_64.dbpkg --expected-manifest packages/hello/package.json
python tools/publish_package.py dist/hello-1.0.0-x86_64.dbpkg --tag hello-v1.0.0-x86_64
python tools/generate_repository.py
```

`publish_package.py` usa `gh release create`, por lo que la URL del asset se obtiene del repositorio real. Después de publicar, se copia esa URL y el SHA-256 de la salida de build al `package.json`; nunca se deben inventar.
