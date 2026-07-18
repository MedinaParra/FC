# FreeCAD Macro Studio (Android)

Prototipo CAD paramétrico nativo para Android, inspirado en la organización de los CAD de escritorio. No contiene código, marcas ni recursos de SolidWorks.

## Funciones

- Interfaz adaptable con barra de operaciones, árbol de modelo, visor y propiedades.
- Visor 3D táctil: arrastrar para orbitar, dos dedos para zoom y desplazamiento.
- Primitivas paramétricas: caja, cilindro, esfera y cono.
- Operaciones de vaciado/corte cilíndrico sobre una pieza.
- Edición de dimensiones, posición y nombre.
- Vistas isométrica, frontal, superior y lateral.
- Generación y exportación de una macro `.FCMacro` para FreeCAD.
- Guardado de proyecto local en JSON.

## Compilar

1. Abrir esta carpeta con Android Studio Ladybug o posterior.
2. Instalar Android SDK 35 si Android Studio lo solicita.
3. Sincronizar Gradle y ejecutar en un equipo Android 8.0 o superior.

Por consola, con Gradle y Android SDK configurados:

```bash
gradle assembleDebug
```

El APK quedará en `app/build/outputs/apk/debug/app-debug.apk`.

Cada envío a la rama `main` también genera automáticamente el artefacto
`FC-Macro-Studio-APK` mediante GitHub Actions.

## Uso rápido

1. Pulse `Caja`, `Cilindro`, `Esfera` o `Cono`.
2. Seleccione una operación en el árbol y edite sus parámetros en el panel inferior.
3. Pulse `Aplicar` para regenerar la vista.
4. Pulse `Macro` para revisar el Python generado y `Exportar` para guardar el archivo.
5. En FreeCAD: **Macro > Macros… > Crear/Editar**, pegue o abra el `.FCMacro` y ejecútelo.

Las operaciones se generan mediante `Part` y document objects estándar de FreeCAD.
