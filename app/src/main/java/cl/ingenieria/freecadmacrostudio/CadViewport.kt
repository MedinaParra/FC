package cl.ingenieria.freecadmacrostudio

import android.content.Context
import android.graphics.*
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import kotlin.math.*

data class V3(val x: Float, val y: Float, val z: Float)
data class Face(val points: List<V3>, val color: Int)

class CadViewport(context: Context) : View(context) {
    var project: CadProject? = null
    var selected = -1
    private var yaw = -0.65f
    private var pitch = 0.45f
    private var zoom = 4.2f
    private var panX = 0f
    private var panY = 0f
    private var lastX = 0f
    private var lastY = 0f
    private val scale = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(d: ScaleGestureDetector): Boolean { zoom = (zoom * d.scaleFactor).coerceIn(0.6f, 18f); invalidate(); return true }
    })
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val edge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 1.5f; color = Color.rgb(55,65,72) }
    private val grid = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeWidth = 1f; color = Color.rgb(222,227,233) }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 13f * resources.displayMetrics.scaledDensity; color = Color.rgb(74,84,94) }

    init { setBackgroundColor(Color.rgb(248,250,252)); isFocusable = true }

    override fun onDraw(c: Canvas) {
        super.onDraw(c)
        drawGrid(c)
        val fs = mutableListOf<Pair<Float, Face>>()
        project?.features?.forEachIndexed { i, f -> if (f.visible) {
            val faces = when (f.type) {
                FeatureType.BOX -> box(f, i == selected)
                FeatureType.CYLINDER, FeatureType.HOLE -> cylinder(f, i == selected, f.type == FeatureType.HOLE)
                FeatureType.SPHERE -> sphere(f, i == selected)
                FeatureType.CONE -> cone(f, i == selected)
            }
            faces.forEach { face -> fs += face.points.map { rotate(it).z }.average().toFloat() to face }
        } }
        fs.sortedBy { it.first }.forEach { (_, face) -> drawFace(c, face) }
        drawAxis(c)
        c.drawText("Arrastre: orbitar  •  Pellizcar: zoom", 16f, height - 18f, textPaint)
    }

    private fun project(v: V3): PointF {
        val r = rotate(v)
        val s = min(width, height) / 180f * zoom
        return PointF(width / 2f + panX + r.x * s, height / 2f + panY - r.y * s)
    }
    private fun rotate(v: V3): V3 {
        val x1 = cos(yaw)*v.x - sin(yaw)*v.z
        val z1 = sin(yaw)*v.x + cos(yaw)*v.z
        return V3(x1, cos(pitch)*v.y - sin(pitch)*z1, sin(pitch)*v.y + cos(pitch)*z1)
    }
    private fun drawFace(c: Canvas, face: Face) {
        if (face.points.size < 3) return
        val p = Path(); face.points.map(::project).forEachIndexed { i, q -> if (i==0) p.moveTo(q.x,q.y) else p.lineTo(q.x,q.y) }; p.close()
        fill.color = face.color; c.drawPath(p, fill); c.drawPath(p, edge)
    }
    private fun shade(base: Int, k: Float) = Color.rgb((Color.red(base)*k).toInt().coerceIn(0,255),(Color.green(base)*k).toInt().coerceIn(0,255),(Color.blue(base)*k).toInt().coerceIn(0,255))
    private fun base(sel: Boolean, cut: Boolean=false) = if (cut) Color.rgb(235,115,105) else if (sel) Color.rgb(255,174,65) else Color.rgb(95,166,211)
    private fun box(f: CadFeature, sel: Boolean): List<Face> {
        val x=f.x-f.a/2; val y=f.y-f.b/2; val z=f.z-f.c/2
        val v=listOf(V3(x,y,z),V3(x+f.a,y,z),V3(x+f.a,y+f.b,z),V3(x,y+f.b,z),V3(x,y,z+f.c),V3(x+f.a,y,z+f.c),V3(x+f.a,y+f.b,z+f.c),V3(x,y+f.b,z+f.c)); val b=base(sel)
        return listOf(Face(listOf(v[0],v[1],v[2],v[3]),shade(b,.72f)),Face(listOf(v[4],v[7],v[6],v[5]),shade(b,1.1f)),Face(listOf(v[0],v[4],v[5],v[1]),shade(b,.85f)),Face(listOf(v[1],v[5],v[6],v[2]),b),Face(listOf(v[2],v[6],v[7],v[3]),shade(b,.92f)),Face(listOf(v[3],v[7],v[4],v[0]),shade(b,.78f)))
    }
    private fun cylinder(f: CadFeature, sel:Boolean, cut:Boolean): List<Face> {
        val seg=28; val r=f.a; val h=f.b; val b=base(sel,cut); val bot=(0 until seg).map { a(it,seg,r,f.z,f) }; val top=(0 until seg).map { a(it,seg,r,f.z+h,f) }; val out=mutableListOf<Face>()
        out += Face(top.reversed(),shade(b,1.1f)); for(i in 0 until seg){val j=(i+1)%seg; out+=Face(listOf(bot[i],bot[j],top[j],top[i]),shade(b,.72f+.3f*(i.toFloat()/seg)))}; return out
    }
    private fun a(i:Int,n:Int,r:Float,z:Float,f:CadFeature):V3 { val q=2f*PI.toFloat()*i/n; return V3(f.x+cos(q)*r,f.y+sin(q)*r,z) }
    private fun cone(f:CadFeature,sel:Boolean):List<Face>{val n=28;val p0=(0 until n).map{a(it,n,f.a,f.z,f)};val p1=(0 until n).map{a(it,n,f.b,f.z+f.c,f)};val b=base(sel);val out=mutableListOf(Face(p1.reversed(),shade(b,1.1f)));for(i in 0 until n){val j=(i+1)%n;out+=Face(listOf(p0[i],p0[j],p1[j],p1[i]),shade(b,.7f+.3f*i/n))};return out}
    private fun spherePoint(f: CadFeature, latitude: Double, longitude: Double) = V3(
        f.x + (f.a * cos(latitude) * cos(longitude)).toFloat(),
        f.y + (f.a * cos(latitude) * sin(longitude)).toFloat(),
        f.z + (f.a * sin(latitude)).toFloat()
    )
    private fun sphere(f: CadFeature, sel: Boolean): List<Face> {
        val out = mutableListOf<Face>()
        val longitudeSegments = 20
        val latitudeSegments = 12
        val color = base(sel)
        for (latitudeIndex in 0 until latitudeSegments) {
            val latitude0 = -PI / 2 + PI * latitudeIndex / latitudeSegments
            val latitude1 = -PI / 2 + PI * (latitudeIndex + 1) / latitudeSegments
            for (longitudeIndex in 0 until longitudeSegments) {
                val longitude0 = 2 * PI * longitudeIndex / longitudeSegments
                val longitude1 = 2 * PI * (longitudeIndex + 1) / longitudeSegments
                out += Face(
                    listOf(
                        spherePoint(f, latitude0, longitude0),
                        spherePoint(f, latitude0, longitude1),
                        spherePoint(f, latitude1, longitude1),
                        spherePoint(f, latitude1, longitude0)
                    ),
                    shade(color, .72f + .35f * latitudeIndex / latitudeSegments)
                )
            }
        }
        return out
    }
    private fun drawGrid(c:Canvas){val step=40f;for(i in -12..12){val a=project(V3(i*step,-480f,0f));val b=project(V3(i*step,480f,0f));c.drawLine(a.x,a.y,b.x,b.y,grid);val d=project(V3(-480f,i*step,0f));val e=project(V3(480f,i*step,0f));c.drawLine(d.x,d.y,e.x,e.y,grid)}}
    private fun drawAxis(c:Canvas){fun line(v:V3,color:Int,label:String){val o=project(V3(0f,0f,0f));val q=project(v);edge.color=color;edge.strokeWidth=4f;c.drawLine(o.x,o.y,q.x,q.y,edge);textPaint.color=color;c.drawText(label,q.x+5,q.y,textPaint)};line(V3(30f,0f,0f),Color.RED,"X");line(V3(0f,30f,0f),Color.rgb(0,150,70),"Y");line(V3(0f,0f,30f),Color.BLUE,"Z");edge.color=Color.rgb(55,65,72);edge.strokeWidth=1.5f}
    fun setView(name:String){when(name){"Frontal"->{yaw=0f;pitch=0f};"Superior"->{yaw=0f;pitch=PI.toFloat()/2};"Lateral"->{yaw=-PI.toFloat()/2;pitch=0f};else->{yaw=-.65f;pitch=.45f}};invalidate()}
    fun fit(){zoom=4.2f;panX=0f;panY=0f;invalidate()}
    override fun onTouchEvent(e:MotionEvent):Boolean{scale.onTouchEvent(e);when(e.actionMasked){MotionEvent.ACTION_DOWN->{lastX=e.x;lastY=e.y};MotionEvent.ACTION_MOVE->if(!scale.isInProgress){val dx=e.x-lastX;val dy=e.y-lastY;if(e.pointerCount>1){panX+=dx;panY+=dy}else{yaw+=dx*.008f;pitch=(pitch+dy*.008f).coerceIn(-1.45f,1.45f)};lastX=e.x;lastY=e.y;invalidate()}};return true}
}
