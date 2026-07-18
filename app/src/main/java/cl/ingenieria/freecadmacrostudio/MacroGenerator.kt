package cl.ingenieria.freecadmacrostudio

import java.util.Locale

object MacroGenerator {
    private fun n(v: Float) = String.format(Locale.US, "%.3f", v)
    private fun id(s: String) = s.replace(Regex("[^A-Za-z0-9_]"), "_").let { if (it.firstOrNull()?.isDigit() == true) "F_$it" else it }

    fun generate(project: CadProject): String = buildString {
        appendLine("# -*- coding: utf-8 -*-")
        appendLine("# Generado por FC Macro Studio para Android")
        appendLine("import FreeCAD as App")
        appendLine("import Part")
        appendLine()
        appendLine("doc = App.newDocument(\"${id(project.name)}\")")
        appendLine("result = None")
        project.features.filter { it.visible }.forEach { f ->
            val v = id(f.name)
            val placement = "App.Vector(${n(f.x)}, ${n(f.y)}, ${n(f.z)})"
            when (f.type) {
                FeatureType.BOX -> appendLine("$v = Part.makeBox(${n(f.a)}, ${n(f.b)}, ${n(f.c)}, $placement)")
                FeatureType.CYLINDER -> appendLine("$v = Part.makeCylinder(${n(f.a)}, ${n(f.b)}, $placement)")
                FeatureType.SPHERE -> appendLine("$v = Part.makeSphere(${n(f.a)}, $placement)")
                FeatureType.CONE -> appendLine("$v = Part.makeCone(${n(f.a)}, ${n(f.b)}, ${n(f.c)}, $placement)")
                FeatureType.HOLE -> {
                    appendLine("$v = Part.makeCylinder(${n(f.a)}, ${n(f.b)}, $placement)")
                    appendLine("if result is not None: result = result.cut($v)")
                    return@forEach
                }
            }
            appendLine("result = $v if result is None else result.fuse($v)")
        }
        appendLine()
        appendLine("if result is not None:")
        appendLine("    obj = doc.addObject(\"PartDesign::Feature\", \"Resultado\")")
        appendLine("    obj.Label = \"${project.name}\"")
        appendLine("    obj.Shape = result.removeSplitter()")
        appendLine("    obj.addProperty(\"App::PropertyString\", \"Generador\")")
        appendLine("    obj.Generador = \"FC Macro Studio Android\"")
        appendLine("doc.recompute()")
        appendLine("Gui.activeDocument().activeView().viewAxonometric()")
        appendLine("Gui.activeDocument().activeView().fitAll()")
    }
}
