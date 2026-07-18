package cl.ingenieria.freecadmacrostudio

import org.json.JSONArray
import org.json.JSONObject

enum class FeatureType(val label: String) { BOX("Caja"), CYLINDER("Cilindro"), SPHERE("Esfera"), CONE("Cono"), HOLE("Corte cilíndrico") }

data class CadFeature(
    var type: FeatureType,
    var name: String,
    var a: Float,
    var b: Float,
    var c: Float,
    var x: Float = 0f,
    var y: Float = 0f,
    var z: Float = 0f,
    var visible: Boolean = true
)

class CadProject(var name: String = "Pieza1") {
    val features = mutableListOf<CadFeature>()

    fun add(type: FeatureType): CadFeature {
        val n = features.count { it.type == type } + 1
        val f = when (type) {
            FeatureType.BOX -> CadFeature(type, "Caja$n", 50f, 40f, 25f)
            FeatureType.CYLINDER -> CadFeature(type, "Cilindro$n", 20f, 50f, 0f)
            FeatureType.SPHERE -> CadFeature(type, "Esfera$n", 25f, 0f, 0f)
            FeatureType.CONE -> CadFeature(type, "Cono$n", 25f, 10f, 50f)
            FeatureType.HOLE -> CadFeature(type, "Corte$n", 8f, 70f, 0f)
        }
        features += f
        return f
    }

    fun toJson(): String {
        val array = JSONArray()
        features.forEach { f -> array.put(JSONObject().apply {
            put("type", f.type.name); put("name", f.name)
            put("a", f.a); put("b", f.b); put("c", f.c)
            put("x", f.x); put("y", f.y); put("z", f.z); put("visible", f.visible)
        }) }
        return JSONObject().put("name", name).put("features", array).toString(2)
    }
}
