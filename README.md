# DreamByte Package Repository

Repositorio oficial de paquetes para **DreamByte Terminal** y **DreamByte OS**. Es estático: el cliente descarga `repository.json`, manifests y assets por HTTPS.

## Estado actual

| Paquete | Tipo | Estado | Arquitectura/artifacto |
|---|---|---|---|
| `hello` | cli | `beta` | `x86_64`, `.dbpkg` real publicado |
| `wget` | cli | `planned` | todavía sin build real |
| `python` | runtime | `planned` | todavía sin runtime real compatible con Android |

`hello` contiene código C real, se compila con GCC, se empaqueta como `.dbpkg`, se verifica y se publica en [GitHub Release hello-v1.0.0-x86_64](https://github.com/jesusxal777-boop/DreamByte-Package-Repository/releases/tag/hello-v1.0.0-x86_64).

## Build system

- `tools/build_package.py`: compila y crea un `.dbpkg` reproducible.
- `tools/validate_package.py`: verifica rutas seguras, manifiesto interno, ejecutable y hashes.
- `tools/publish_package.py`: publica el asset con `gh release` y muestra su URL real.
- `tools/generate_repository.py`: valida manifests y genera `repository.json`; no se edita manualmente.
- `tools/pkg.py`: cliente de referencia local para `update`, `search`, `info` e `install`.

El formato del archivo está documentado en [`docs/dbpkg-format.md`](docs/dbpkg-format.md) y el formato de catálogo en [`docs/package-format.md`](docs/package-format.md).

## Prueba reproducible local

```bash
rm -rf dist .dreambyte-install
python tools/build_package.py packages/hello --output-dir dist
python tools/validate_package.py dist/hello-1.0.0-x86_64.dbpkg --expected-manifest packages/hello/package.json
python tools/generate_repository.py --check
python tools/pkg.py --repo-root . update
python tools/pkg.py --repo-root . search hello
python tools/pkg.py --repo-root . info hello
python tools/pkg.py --repo-root . install hello --prefix .dreambyte-install
```

La última orden verifica SHA-256, rechaza rutas inseguras, instala dentro de un prefijo privado y ejecuta `bin/hello`.

## CI

GitHub Actions ejecuta `python tools/generate_repository.py --check`, valida todos los `.dbpkg` presentes en `dist/` y comprueba JSON, nombres, versiones, arquitecturas, dependencias, HTTPS y consistencia de hashes.

Los paquetes `stable`/`beta` deben tener un artefacto real y no pueden depender de paquetes `planned` o `metadata-only`. `wget` y `python` permanecen `planned` hasta que exista un build legítimo e instalable para sus arquitecturas declaradas.
