# Alcance del prototipo 0.1

Este proyecto implementa el núcleo de una aplicación generadora de macros y no intenta ejecutar FreeCAD dentro de Android. El teléfono construye un modelo paramétrico ligero, lo previsualiza y genera Python reproducible para ejecutarlo posteriormente en FreeCAD de escritorio.

## Correspondencia de parámetros

| Operación Android | API generada en FreeCAD |
|---|---|
| Caja | `Part.makeBox(longitud, ancho, alto, posición)` |
| Cilindro | `Part.makeCylinder(radio, altura, posición)` |
| Esfera | `Part.makeSphere(radio, posición)` |
| Cono | `Part.makeCone(radio1, radio2, altura, posición)` |
| Corte cilíndrico | `resultado.cut(cilindro)` |

## Próximas iteraciones recomendadas

1. Croquis 2D con línea, círculo, arco, cotas y restricciones.
2. Extrusión y revolución de croquis arbitrarios.
3. Redondeo, chaflán, patrón lineal/circular y simetría.
4. Importación de una macro existente al árbol de operaciones.
5. Ensambles y biblioteca de componentes SKF.
6. Sincronización opcional con un backend que ejecute FreeCAD/Code_Aster.
