package cl.ingenieria.freecadmacrostudio

import android.app.*
import android.content.*
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.*
import android.widget.*
import java.io.OutputStreamWriter

class MainActivity : Activity() {
    private val project = CadProject()
    private lateinit var viewport: CadViewport
    private lateinit var tree: LinearLayout
    private lateinit var props: LinearLayout
    private lateinit var status: TextView
    private var selected = -1
    private var pendingText = ""
    private val fields = mutableListOf<EditText>()

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        project.add(FeatureType.BOX)
        viewport = CadViewport(this).apply { project = this@MainActivity.project }
        setContentView(buildUi())
        select(0)
    }

    private fun buildUi(): View {
        val root = LinearLayout(this).apply { orientation=LinearLayout.VERTICAL; setBackgroundColor(Color.rgb(236,239,243)) }
        root.addView(topBar(), LinearLayout.LayoutParams(-1, dp(54)))
        root.addView(operationBar(), LinearLayout.LayoutParams(-1, dp(64)))
        val content = if (resources.configuration.orientation == 2) landscapeContent() else portraitContent()
        root.addView(content, LinearLayout.LayoutParams(-1,0,1f))
        status = TextView(this).apply { text="Listo • Pieza • MMGS"; setPadding(dp(12),0,dp(12),0); gravity=Gravity.CENTER_VERTICAL; setTextColor(Color.DKGRAY); textSize=12f }
        root.addView(status, LinearLayout.LayoutParams(-1,dp(30)))
        return root
    }

    private fun topBar() = LinearLayout(this).apply {
        gravity=Gravity.CENTER_VERTICAL; setPadding(dp(10),0,dp(6),0); setBackgroundColor(Color.rgb(38,55,70))
        addView(TextView(this@MainActivity).apply { text="FC  MACRO STUDIO"; setTextColor(Color.WHITE); textSize=19f }, LinearLayout.LayoutParams(0,-1,1f))
        addView(button("Nuevo") { confirmNew() }); addView(button("Guardar") { saveProject() }); addView(button("Macro") { previewMacro() }); addView(button("Exportar") { exportMacro() })
    }

    private fun operationBar() = HorizontalScrollView(this).apply {
        isHorizontalScrollBarEnabled=false; setBackgroundColor(Color.WHITE)
        addView(LinearLayout(this@MainActivity).apply {
            gravity=Gravity.CENTER_VERTICAL; setPadding(dp(6),0,dp(6),0)
            addView(tool("▣","Caja") { add(FeatureType.BOX) }); addView(tool("◉","Cilindro") { add(FeatureType.CYLINDER) }); addView(tool("●","Esfera") { add(FeatureType.SPHERE) }); addView(tool("△","Cono") { add(FeatureType.CONE) }); addView(tool("⊖","Corte") { add(FeatureType.HOLE) })
            addView(divider()); addView(tool("⌂","Ajustar") { viewport.fit() }); addView(tool("◇","Iso") { viewport.setView("Iso") }); addView(tool("□","Frontal") { viewport.setView("Frontal") }); addView(tool("▱","Superior") { viewport.setView("Superior") }); addView(tool("▯","Lateral") { viewport.setView("Lateral") })
        })
    }

    private fun landscapeContent(): View {
        tree = LinearLayout(this).apply { orientation=LinearLayout.VERTICAL }
        props = LinearLayout(this).apply { orientation=LinearLayout.VERTICAL }
        val row=LinearLayout(this)
        row.addView(panel("ÁRBOL DE OPERACIONES", tree), LinearLayout.LayoutParams(dp(245),-1))
        row.addView(viewport, LinearLayout.LayoutParams(0,-1,1f))
        row.addView(panel("PROPIEDADES", props), LinearLayout.LayoutParams(dp(260),-1))
        return row
    }
    private fun portraitContent(): View {
        tree = LinearLayout(this).apply { orientation=LinearLayout.VERTICAL }
        props = LinearLayout(this).apply { orientation=LinearLayout.VERTICAL }
        return LinearLayout(this).apply { orientation=LinearLayout.VERTICAL
            val side=LinearLayout(this@MainActivity)
            side.addView(panel("OPERACIONES",tree),LinearLayout.LayoutParams(0,-1,1f)); side.addView(panel("PROPIEDADES",props),LinearLayout.LayoutParams(0,-1,1f))
            addView(side,LinearLayout.LayoutParams(-1,dp(220))); addView(viewport,LinearLayout.LayoutParams(-1,0,1f))
        }
    }
    private fun panel(title:String, body:LinearLayout)=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL;setBackgroundColor(Color.WHITE)
        addView(TextView(this@MainActivity).apply{text=title;setTextColor(Color.rgb(45,70,90));textSize=12f;gravity=Gravity.CENTER_VERTICAL;setPadding(dp(10),0,0,0);setBackgroundColor(Color.rgb(218,226,234))},LinearLayout.LayoutParams(-1,dp(32)))
        addView(ScrollView(this@MainActivity).apply{addView(body)},LinearLayout.LayoutParams(-1,0,1f))
    }

    private fun refreshTree() { tree.removeAllViews(); tree.addView(treeRow("◆  ${project.name}",-1,true)); tree.addView(treeRow("   ▸ Origen",-2,false)); tree.addView(treeRow("      Alzado",-2,false)); tree.addView(treeRow("      Planta",-2,false)); tree.addView(treeRow("      Vista lateral",-2,false)); project.features.forEachIndexed { i,f -> tree.addView(treeRow("${if(f.visible) "◉" else "○"}  ${f.name}",i,i==selected)) } }
    private fun treeRow(label:String,index:Int,on:Boolean)=TextView(this).apply { text=label;textSize=14f;gravity=Gravity.CENTER_VERTICAL;setPadding(dp(14),0,dp(4),0);setTextColor(if(on) Color.rgb(20,90,145) else Color.DKGRAY);setBackgroundColor(if(on) Color.rgb(221,238,250) else Color.TRANSPARENT);setOnClickListener{if(index>=0)select(index)};setOnLongClickListener{if(index>=0){toggle(index);true}else false} }.also{it.layoutParams=LinearLayout.LayoutParams(-1,dp(38))}

    private fun select(i:Int){selected=i;viewport.selected=i;refreshTree();refreshProps();viewport.invalidate();status.text="Editando ${project.features[i].name} • MMGS"}
    private fun refreshProps(){props.removeAllViews();fields.clear();if(selected !in project.features.indices)return;val f=project.features[selected]
        addField("Nombre",f.name); when(f.type){FeatureType.BOX->{addField("Longitud (mm)",f.a);addField("Ancho (mm)",f.b);addField("Alto (mm)",f.c)};FeatureType.CYLINDER,FeatureType.HOLE->{addField("Radio (mm)",f.a);addField("Altura (mm)",f.b)};FeatureType.SPHERE->addField("Radio (mm)",f.a);FeatureType.CONE->{addField("Radio 1 (mm)",f.a);addField("Radio 2 (mm)",f.b);addField("Altura (mm)",f.c)}}
        addField("Posición X",f.x);addField("Posición Y",f.y);addField("Posición Z",f.z)
        props.addView(button("Aplicar cambios") { applyFields() },LinearLayout.LayoutParams(-1,dp(44)));props.addView(button("Duplicar") { duplicate() },LinearLayout.LayoutParams(-1,dp(44)));props.addView(button("Eliminar") { deleteSelected() },LinearLayout.LayoutParams(-1,dp(44)))
    }
    private fun addField(label:String,value:Any){props.addView(TextView(this).apply{text=label;textSize=12f;setTextColor(Color.DKGRAY);setPadding(dp(10),dp(6),0,0)});val e=EditText(this).apply{setText(value.toString());textSize=14f;setSingleLine();setPadding(dp(10),0,dp(8),0)};fields+=e;props.addView(e,LinearLayout.LayoutParams(-1,dp(40)))}
    private fun applyFields(){val f=project.features[selected];f.name=fields[0].text.toString().ifBlank{f.name};val nums=fields.drop(1).map{it.text.toString().replace(',','.').toFloatOrNull()};var k=0
        when(f.type){FeatureType.BOX->{f.a=pos(nums[k++],f.a);f.b=pos(nums[k++],f.b);f.c=pos(nums[k++],f.c)};FeatureType.CYLINDER,FeatureType.HOLE->{f.a=pos(nums[k++],f.a);f.b=pos(nums[k++],f.b)};FeatureType.SPHERE->f.a=pos(nums[k++],f.a);FeatureType.CONE->{f.a=pos(nums[k++],f.a);f.b=pos(nums[k++],f.b);f.c=pos(nums[k++],f.c)}};f.x=nums[k++]?:f.x;f.y=nums[k++]?:f.y;f.z=nums[k]?:f.z;refreshTree();viewport.invalidate();toast("Modelo regenerado") }
    private fun pos(v:Float?,old:Float)=if(v!=null&&v>0)v else old
    private fun add(t:FeatureType){select(project.features.indexOf(project.add(t)))}
    private fun toggle(i:Int){project.features[i].visible=!project.features[i].visible;refreshTree();viewport.invalidate()}
    private fun duplicate(){val f=project.features[selected];project.features+=f.copy(name=f.name+" copia",x=f.x+10);select(project.features.lastIndex)}
    private fun deleteSelected(){if(project.features.size==1){toast("La pieza debe conservar una operación");return};project.features.removeAt(selected);select(selected.coerceAtMost(project.features.lastIndex))}
    private fun confirmNew(){AlertDialog.Builder(this).setTitle("Nueva pieza").setMessage("¿Descartar la pieza actual?").setNegativeButton("Cancelar",null).setPositiveButton("Nueva"){_,_->project.features.clear();project.add(FeatureType.BOX);select(0)}.show()}
    private fun previewMacro(){val code=MacroGenerator.generate(project);AlertDialog.Builder(this).setTitle("Macro FreeCAD generada").setView(ScrollView(this).apply{addView(TextView(this@MainActivity).apply{text=code;setTextIsSelectable(true);typeface=android.graphics.Typeface.MONOSPACE;setPadding(dp(16),dp(12),dp(16),dp(12))})}).setNegativeButton("Cerrar",null).setPositiveButton("Exportar"){_,_->exportMacro()}.show()}
    private fun exportMacro(){pendingText=MacroGenerator.generate(project);startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply{addCategory(Intent.CATEGORY_OPENABLE);type="text/x-python";putExtra(Intent.EXTRA_TITLE,"${project.name}.FCMacro")},91)}
    private fun saveProject(){pendingText=project.toJson();startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply{addCategory(Intent.CATEGORY_OPENABLE);type="application/json";putExtra(Intent.EXTRA_TITLE,"${project.name}.fcmstudio.json")},92)}
    override fun onActivityResult(requestCode:Int,resultCode:Int,data:Intent?){super.onActivityResult(requestCode,resultCode,data);if(resultCode==RESULT_OK)data?.data?.let{write(it,pendingText)}}
    private fun write(uri:Uri,text:String){try{contentResolver.openOutputStream(uri)?.use{OutputStreamWriter(it).use{w->w.write(text)}};toast("Archivo guardado correctamente")}catch(e:Exception){toast("No se pudo guardar: ${e.message}")}}
    private fun button(label:String,action:()->Unit)=Button(this).apply{text=label;textSize=12f;isAllCaps=false;setOnClickListener{action()};minWidth=0;minimumWidth=0}
    private fun tool(icon:String,label:String,action:()->Unit)=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;gravity=Gravity.CENTER;setPadding(dp(9),0,dp(9),0);addView(TextView(this@MainActivity).apply{text=icon;textSize=24f;gravity=Gravity.CENTER;setTextColor(Color.rgb(32,99,145))});addView(TextView(this@MainActivity).apply{text=label;textSize=10f;gravity=Gravity.CENTER});setOnClickListener{action()}}
    private fun divider()=View(this).apply{setBackgroundColor(Color.LTGRAY);layoutParams=LinearLayout.LayoutParams(dp(1),dp(45)).apply{setMargins(dp(7),0,dp(7),0)}}
    private fun dp(v:Int)=(v*resources.displayMetrics.density).toInt()
    private fun toast(s:String)=Toast.makeText(this,s,Toast.LENGTH_SHORT).show()
}
