# -*- coding: utf-8 -*-
"""Genera en FreeCAD un pórtico completo de dos aguas con conexiones R2.

Cotas principales conservadas del avance:
- separación de ejes de columnas: 9211.400 mm
- altura de columnas: 9320.000 mm
- cara superior de la última viga horizontal: Z=6660.000 mm
- punto interior de cumbrera: Z=9895.000 mm
- diferencia vertical solicitada: 3235.000 mm
- vigas de agua: perfil conformado de 300 x 200 mm

Las conexiones de alero y cumbrera interpretan las vistas isométricas entregadas:
placas superiores prolongadas, placas de testa, cubrejuntas, asientos inferiores,
cartelas y pernos. Modelo conceptual editable; no fabricar sin cálculo.
"""
import os, math, shutil
import FreeCAD as App
import Part, Import
try:
    import Mesh, MeshPart
except Exception:
    Mesh = MeshPart = None

HERE=os.path.dirname(os.path.abspath(__file__))
OUT_DIR=os.environ.get('PORTICO_OUT',os.path.join(HERE,'salida_portico_r2'))
os.makedirs(OUT_DIR,exist_ok=True)
BASE='Portico_Dos_Aguas_Conexiones_R2'
P=lambda ext: os.path.join(OUT_DIR,BASE+ext)
OUT_FCSTD=P('.FCStd'); OUT_STEP=P('.step'); OUT_STP=P('.stp')
OUT_IGES=P('.iges'); OUT_IGS=P('.igs'); OUT_BREP=P('.brep')
OUT_STL=P('.stl'); OUT_OBJ=P('.obj'); OUT_PLY=P('.ply'); OUT_OFF=P('.off'); OUT_3MF=P('.3mf')
OUT_REPORT=os.path.join(OUT_DIR,'Validacion_Portico_Conexiones_R2.txt')
OUT_MEM=os.path.join(OUT_DIR,'Memoria_Dimensional_Portico_R2.txt')

STEEL=(0.72,0.74,0.78); ROOF=(0.64,0.68,0.75); PLATE=(0.46,0.50,0.58)
BOLT=(0.18,0.20,0.24); GUSSET=(0.56,0.60,0.67)
def V(x=0,y=0,z=0): return App.Vector(float(x),float(y),float(z))
def neg(v): return V(-v.x,-v.y,-v.z)
def unit(v):
    q=V(v.x,v.y,v.z)
    if q.Length<1e-9: raise ValueError('vector nulo')
    q.normalize(); return q

def set_color(o,c):
    try:
        o.ViewObject.ShapeColor=c; o.ViewObject.LineColor=(0.12,0.12,0.12); o.ViewObject.DisplayMode='Flat Lines'
    except Exception: pass

def add_feature(doc,g,name,label,shape,color=STEEL,desc=''):
    if shape is None or shape.isNull(): raise ValueError('forma nula '+name)
    o=doc.addObject('Part::Feature',name); o.Label=label; o.Shape=shape
    o.addProperty('App::PropertyString','Revision','Proyecto'); o.Revision='R2'
    o.addProperty('App::PropertyString','Estado','Proyecto'); o.Estado='Geometría conceptual; verificar por cálculo antes de fabricar.'
    if desc:
        o.addProperty('App::PropertyString','Descripcion','Proyecto'); o.Descripcion=desc
    g.addObject(o); set_color(o,color); return o

def oriented(shape,center,ex,eu,en):
    ex,eu,en=unit(ex),unit(eu),unit(en)
    calc=unit(ex.cross(eu))
    if calc.dot(en)<0: ex=neg(ex); calc=unit(ex.cross(eu))
    shape.Placement=App.Placement(center,App.Rotation(ex,eu,calc,'ZXY'))
    return shape

def oriented_box(wx,lu,tn,c,ex,eu,en):
    sh=Part.makeBox(wx,lu,tn,V(-wx/2,-lu/2,-tn/2)); return oriented(sh,c,ex,eu,en)

def box_center(dx,dy,dz,c): return Part.makeBox(dx,dy,dz,V(c.x-dx/2,c.y-dy/2,c.z-dz/2))
def point(base,eu,en,du=0,dn=0,dx=0): return base.add(eu.multiply(du)).add(en.multiply(dn)).add(V(dx,0,0))

def cyl_between(p1,p2,r):
    vec=p2.sub(p1); sh=Part.makeCylinder(r,vec.Length)
    sh.Placement=App.Placement(p1,App.Rotation(V(0,0,1),vec)); return sh

def bolt_shape(p1,p2,d=20,head_t=9):
    vec=p2.sub(p1); uv=unit(vec); hd=d*1.65
    s=cyl_between(p1,p2,d/2)
    a=Part.makeCylinder(hd/2,head_t); a.Placement=App.Placement(p1.sub(uv.multiply(head_t)),App.Rotation(V(0,0,1),vec))
    b=Part.makeCylinder(hd/2,head_t); b.Placement=App.Placement(p2,App.Rotation(V(0,0,1),vec))
    return Part.makeCompound([s,a,b])
def add_bolt(doc,g,name,label,p1,p2,d=20): return add_feature(doc,g,name,label,bolt_shape(p1,p2,d),BOLT)
def add_normal_bolt(doc,g,prefix,i,c,n,span=120,d=20):
    n=unit(n); return add_bolt(doc,g,'%s_%02d'%(prefix,i),'%s M%d'%(prefix,int(d)),c.sub(n.multiply(span/2)),c.add(n.multiply(span/2)),d)
def gusset_yz(points,xc,t=12):
    pts=[V(xc-t/2,y,z) for y,z in points]; pts.append(pts[0])
    return Part.Face(Part.makePolygon(pts)).extrude(V(t,0,0))

def formed_profile(width,depth,length,wall=8,rib=12):
    parts=[
        Part.makeBox(wall,length,depth-2*wall,V(-width/2,-length/2,-depth/2+wall)),
        Part.makeBox(wall,length,depth-2*wall,V(width/2-wall,-length/2,-depth/2+wall)),
        Part.makeBox(width,length,wall,V(-width/2,-length/2,-depth/2)),
        Part.makeBox(width,length,wall,V(-width/2,-length/2,depth/2-wall)),
    ]
    rw=max(18.0,width*0.13); rh=min(rib,depth*0.04)
    for x in (-width*0.23,width*0.23):
        parts.append(Part.makeBox(rw,length,rh,V(x-rw/2,-length/2,depth/2-rh)))
        parts.append(Part.makeBox(rw,length,rh,V(x-rw/2,-length/2,-depth/2)))
    rz=max(34.0,depth*0.10); rt=min(6.0,wall)
    for x0 in (-width/2,width/2-rt): parts.append(Part.makeBox(rt,length,rz,V(x0,-length/2,-rz/2)))
    return Part.makeCompound(parts)

def add_profile(doc,g,name,label,width,depth,p0,p1,color,desc=''):
    vec=p1.sub(p0); L=vec.Length; eu=unit(vec); ex=V(1,0,0)
    if abs(eu.dot(ex))>0.95: ex=V(0,1,0)
    en=unit(ex.cross(eu)); ex=unit(eu.cross(en))
    sh=oriented(formed_profile(width,depth,L),p0.add(vec.multiply(0.5)),ex,eu,en)
    return add_feature(doc,g,name,label,sh,color,desc)

YL=0.0; YR=9211.4; YC=4605.7
H=9320.0; UPPER_TOP=6660.0; RIDGE_INNER=9895.0
COL_ENVELOPE=550.0; WIDTH=200.0; ROOF_DEPTH=300.0
HALF=(YR-YL)/2; RISE=RIDGE_INNER-H
ANGLE=math.atan2(RISE,HALF); DEG=math.degrees(ANGLE); c=math.cos(ANGLE); s=math.sin(ANGLE)
uL=V(0,c,s); nL=V(0,-s,c); xL=V(1,0,0)
uR=V(0,-c,s); nR=V(0,s,c); xR=V(-1,0,0)
EAVE_AXIS=H+(ROOF_DEPTH/2)*c; RIDGE_AXIS=RIDGE_INNER+(ROOF_DEPTH/2)*c
EL=V(0,YL,EAVE_AXIS); ER=V(0,YR,EAVE_AXIS); RC=V(0,YC,RIDGE_AXIS)

doc=App.newDocument('Portico_Dos_Aguas_Conexiones_R2'); doc.Label='Pórtico dos aguas - conexiones R2'
g_main=doc.addObject('App::Part','Estructura_Principal'); g_main.Label='Estructura principal'
g_roof=doc.addObject('App::Part','Cubierta_Dos_Aguas'); g_roof.Label='Cubierta dos aguas 300x200'
g_hconn=doc.addObject('App::Part','Conexiones_Vigas_Horizontales'); g_hconn.Label='Conexiones vigas horizontales'
g_base=doc.addObject('App::Part','Bases_Anclajes'); g_base.Label='Bases y anclajes'
g_r2=doc.addObject('App::Part','Conexiones_R2'); g_r2.Label='Conexiones R2 de alero y cumbrera'

add_profile(doc,g_main,'Columna_Izquierda','Columna izquierda nominal 520x200',WIDTH,COL_ENVELOPE,V(0,YL,0),V(0,YL,H),STEEL)
add_profile(doc,g_main,'Columna_Derecha','Columna derecha nominal 520x200',WIDTH,COL_ENVELOPE,V(0,YR,0),V(0,YR,H),STEEL)
clear_start=275.0; clear_end=YR-275.0
for name,label,zc in [('Viga_Horizontal_Inferior','Viga horizontal inferior',3235.0),('Viga_Horizontal_Superior','Viga horizontal superior',6385.0)]:
    add_profile(doc,g_main,name,label,WIDTH,550,V(0,clear_start,zc),V(0,clear_end,zc),STEEL)
run_gap=8.0; slope_len=math.hypot(HALF,RISE); gap_along=run_gap/c
add_profile(doc,g_roof,'Viga_Agua_Izquierda','Viga de agua izquierda 300x200',WIDTH,ROOF_DEPTH,EL,EL.add(uL.multiply(slope_len-gap_along)),ROOF)
add_profile(doc,g_roof,'Viga_Agua_Derecha','Viga de agua derecha 300x200',WIDTH,ROOF_DEPTH,ER,ER.add(uR.multiply(slope_len-gap_along)),ROOF)

for side,y in [('Izq',YL),('Der',YR)]:
    add_feature(doc,g_base,'Placa_Base_'+side,'Placa base '+side+' 760x980x32',box_center(760,980,32,V(0,y,-16)),PLATE)
    coords=[(-300,-400),(0,-400),(300,-400),(-300,400),(0,400),(300,400),(-300,0),(300,0)]
    for i,(x,dy) in enumerate(coords,1): add_bolt(doc,g_base,'Anclaje_%s_%02d'%(side,i),'Anclaje %s M24'%side,V(x,y+dy,-430),V(x,y+dy,55),24)

for lev,zc in [(1,3235.0),(2,6385.0)]:
    for side,yface,ya,yb in [('Izq',283,-75,35),('Der',YR-283,YR-35,YR+75)]:
        add_feature(doc,g_hconn,'Placa_Viga%d_%s'%(lev,side),'Placa viga-columna nivel %d %s'%(lev,side),box_center(340,16,680,V(0,yface,zc)),PLATE)
        idx=1
        for x in (-120,120):
            for dz in (-205,-70,70,205):
                add_bolt(doc,g_hconn,'Perno_Viga%d_%s_%02d'%(lev,side,idx),'Perno viga-columna M20',V(x,ya,zc+dz),V(x,yb,zc+dz),20); idx+=1

def alero(side,eave,eu,en,ex,ycol):
    g=doc.addObject('App::Part','Alero_R2_'+side); g.Label='Conexión de alero R2 '+side; g_r2.addObject(g)
    add_feature(doc,g,'Alero_%s_PlacaSuperior'%side,'Placa superior alero '+side,oriented_box(700,940,16,point(eave,eu,en,270,158),ex,eu,en),PLATE)
    add_feature(doc,g,'Alero_%s_CubrejuntaSuperior'%side,'Cubrejunta superior alero '+side,oriented_box(360,1100,12,point(eave,eu,en,890,157),ex,eu,en),PLATE)
    add_feature(doc,g,'Alero_%s_PlacaTesta'%side,'Placa de testa alero '+side,oriented_box(480,16,390,point(eave,eu,en,105,0),ex,eu,en),PLATE)
    for i,xoff in enumerate((-106,106),1): add_feature(doc,g,'Alero_%s_PlacaLateral_%d'%(side,i),'Placa lateral alero '+side,oriented_box(12,520,370,point(eave,eu,en,300,-5,xoff),ex,eu,en),PLATE)
    add_feature(doc,g,'Alero_%s_AsientoInferior'%side,'Asiento inferior alero '+side,oriented_box(540,560,16,point(eave,eu,en,295,-158),ex,eu,en),PLATE)
    add_feature(doc,g,'Alero_%s_CubrejuntaInferior'%side,'Cubrejunta inferior alero '+side,oriented_box(330,700,12,point(eave,eu,en,760,-157),ex,eu,en),PLATE)
    yface=ycol+(283 if side=='Izq' else -283)
    add_feature(doc,g,'Alero_%s_RespaldoColumna'%side,'Respaldo de columna alero '+side,box_center(520,16,330,V(0,yface,H-85)),PLATE)
    idx=1
    for du in (85,590):
        for dx in (-240,-80,80,240): add_normal_bolt(doc,g,'Alero_%s_PernoSuperior'%side,idx,point(eave,eu,en,du,158,dx),en,115,20); idx+=1
    idx=1
    for dx in (-145,145):
        for dn in (-88,88):
            q=point(eave,eu,en,105,dn,dx); add_bolt(doc,g,'Alero_%s_PernoTesta_%02d'%(side,idx),'Perno testa alero M20',q.sub(eu.multiply(75)),q.add(eu.multiply(75)),20); idx+=1
    idx=1
    for du in (125,430):
        for dx in (-180,180): add_normal_bolt(doc,g,'Alero_%s_PernoAsiento'%side,idx,point(eave,eu,en,du,-158,dx),en,115,20); idx+=1
    idx=1
    for du in (165,390):
        for dn in (-78,78):
            q=point(eave,eu,en,du,dn); add_bolt(doc,g,'Alero_%s_PernoLateral_%02d'%(side,idx),'Perno lateral alero M20',q.add(V(-165,0,0)),q.add(V(165,0,0)),20); idx+=1
    sy=1 if side=='Izq' else -1
    pts=[(ycol+sy*285,H-900),(ycol+sy*285,H-55),(ycol+sy*1080,H+55+795*math.tan(ANGLE))]
    for i,x in enumerate((-78,78),1): add_feature(doc,g,'Alero_%s_Cartela_%d'%(side,i),'Cartela triangular alero '+side,gusset_yz(pts,x,12),GUSSET)

alero('Izq',EL,uL,nL,xL,YL); alero('Der',ER,uR,nR,xR,YR)

g=doc.addObject('App::Part','Cumbrera_R2'); g.Label='Conexión central de cumbrera R2'; g_r2.addObject(g)
dL=neg(uL); dR=neg(uR)
for side,d,n,ex in [('Izq',dL,nL,xL),('Der',dR,nR,xR)]:
    add_feature(doc,g,'Cumbrera_PlacaSuperior_'+side,'Placa superior quebrada cumbrera '+side,oriented_box(600,900,16,point(RC,d,n,430,158),ex,d,n),PLATE)
    add_feature(doc,g,'Cumbrera_CubrejuntaSuperior_'+side,'Cubrejunta superior cumbrera '+side,oriented_box(360,1050,12,point(RC,d,n,1030,157),ex,d,n),PLATE)
    add_feature(doc,g,'Cumbrera_AsientoInferior_'+side,'Asiento inferior cumbrera '+side,oriented_box(520,650,14,point(RC,d,n,325,-158),ex,d,n),PLATE)
    add_feature(doc,g,'Cumbrera_CubrejuntaInferior_'+side,'Cubrejunta inferior cumbrera '+side,oriented_box(340,650,12,point(RC,d,n,780,-157),ex,d,n),PLATE)
    idx=1
    for du in (170,610):
        for dx in (-225,-75,75,225): add_normal_bolt(doc,g,'Cumbrera_PernoSuperior_'+side,idx,point(RC,d,n,du,158,dx),n,120,20); idx+=1
    idx=1
    for du in (155,485):
        for dx in (-175,175): add_normal_bolt(doc,g,'Cumbrera_PernoAsiento_'+side,idx,point(RC,d,n,du,-158,dx),n,115,20); idx+=1
for side,dy in [('Izq',-12),('Der',12)]: add_feature(doc,g,'Cumbrera_PlacaTesta_'+side,'Placa de testa central '+side,box_center(480,16,400,V(0,YC+dy,RIDGE_AXIS)),PLATE)
idx=1
for x in (-165,165):
    for dz in (-128,-43,43,128): add_bolt(doc,g,'Cumbrera_PernoTesta_%02d'%idx,'Perno central cumbrera M20',V(x,YC-58,RIDGE_AXIS+dz),V(x,YC+58,RIDGE_AXIS+dz),20); idx+=1
for i,x in enumerate((-108,108),1): add_feature(doc,g,'Cumbrera_PlacaLateral_%d'%i,'Placa lateral central',box_center(12,720,350,V(x,YC,RIDGE_AXIS-15)),PLATE)
for side,sgn in [('Izq',-1),('Der',1)]:
    pts=[(YC+sgn*18,RIDGE_AXIS-185),(YC+sgn*18,RIDGE_AXIS-520),(YC+sgn*690,RIDGE_AXIS-260-690*math.tan(ANGLE))]
    for i,x in enumerate((-74,74),1): add_feature(doc,g,'Cumbrera_Cartela_%s_%d'%(side,i),'Cartela inferior cumbrera '+side,gusset_yz(pts,x,12),GUSSET)
add_feature(doc,g,'Cumbrera_TapaCentral','Tapa central cumbrera',box_center(620,160,12,V(0,YC,RIDGE_AXIS+174)),PLATE)

ss=doc.addObject('Spreadsheet::Sheet','Parametros'); ss.Label='Cotas y supuestos'
rows=[('PARÁMETRO','VALOR'),('Separación ejes columnas','9211.400 mm'),('Altura columnas','9320.000 mm'),('Cara superior última viga','6660.000 mm'),('Ascenso a cumbrera interior','3235.000 mm'),('Cumbrera interior Z','9895.000 mm'),('Columnas','perfil nominal 520x200'),('Vigas de agua','300x200'),('Pendiente por agua','%.6f grados'%DEG),('Revisión','R2 conexiones según vistas isométricas')]
for i,(a,b) in enumerate(rows,1): ss.set('A%d'%i,a); ss.set('B%d'%i,b)
ss.setColumnWidth('A',360); ss.setColumnWidth('B',500)
params=doc.addObject('App::FeaturePython','Datos_Geometricos'); params.Label='Datos geométricos principales'
for n,v,t in [('SeparacionEjes',YR-YL,'App::PropertyLength'),('AlturaColumnas',H,'App::PropertyLength'),('UltimaVigaSuperior',UPPER_TOP,'App::PropertyLength'),('CumbreraInterior',RIDGE_INNER,'App::PropertyLength'),('AscensoCumbrera',RIDGE_INNER-UPPER_TOP,'App::PropertyLength'),('AnguloCubierta',DEG,'App::PropertyAngle')]:
    params.addProperty(t,n,'Dimensiones'); setattr(params,n,v)
doc.recompute()

valid=[]; invalid=[]; null=[]
for o in doc.Objects:
    if o.TypeId!='Part::Feature': continue
    sh=getattr(o,'Shape',None)
    if sh is None or sh.isNull(): null.append(o.Name); continue
    try:
        if sh.Volume<=0: continue
        if sh.isValid(): valid.append(o)
        else: invalid.append(o.Name)
    except Exception: invalid.append(o.Name)
if invalid: raise RuntimeError('Formas inválidas: '+', '.join(invalid))
if len(valid)<50: raise RuntimeError('Muy pocos objetos válidos: %d'%len(valid))
doc.saveAs(OUT_FCSTD)
Part.export(valid,OUT_STEP); shutil.copy2(OUT_STEP,OUT_STP)
Part.export(valid,OUT_IGES); shutil.copy2(OUT_IGES,OUT_IGS)
compound=Part.makeCompound([o.Shape for o in valid]); compound.exportBrep(OUT_BREP)
mesh_status=[]
if Mesh and MeshPart:
    try:
        mesh=MeshPart.meshFromShape(Shape=compound,LinearDeflection=1.8,AngularDeflection=0.523599,Relative=False)
        for path in (OUT_STL,OUT_OBJ,OUT_PLY,OUT_OFF,OUT_3MF):
            try: mesh.write(path); mesh_status.append(os.path.basename(path)+' OK')
            except Exception as e: mesh_status.append(os.path.basename(path)+' ERROR '+str(e))
    except Exception as e: mesh_status.append('mallado ERROR '+str(e))
else: mesh_status.append('Mesh/MeshPart no disponible')
step_check='NO'
try:
    chk=App.newDocument('CheckSTEP'); Import.insert(OUT_STEP,chk.Name); chk.recompute()
    nvalid=sum(1 for o in chk.Objects if getattr(o,'Shape',None) is not None and not o.Shape.isNull() and o.Shape.isValid())
    step_check='OK, %d objeto(s) válido(s)'%nvalid; App.closeDocument(chk.Name)
except Exception as e: step_check='ERROR '+str(e)

with open(OUT_MEM,'w',encoding='utf-8') as f:
    f.write('MEMORIA DIMENSIONAL - PORTICO DOS AGUAS R2\n==========================================\n\n')
    f.write('Separación ejes columnas: 9211.400 mm\nAltura columnas: 9320.000 mm\n')
    f.write('Cara superior última viga: 6660.000 mm\nPunto interior cumbrera: 9895.000 mm\n')
    f.write('Diferencia vertical: 3235.000 mm\nVigas de agua: 300x200 mm\nPendiente: %.6f grados\n\n'%DEG)
    f.write('Aleros R2: placa superior, cubrejunta, placa de testa, placas laterales, asiento inferior, cartelas y pernos.\n')
    f.write('Cumbrera R2: placas superiores quebradas, placas de testa centrales, asientos, cubrejuntas, cartelas y pernos.\n\n')
    f.write('Modelo conceptual. Verificar estructuralmente antes de fabricar.\n')
with open(OUT_REPORT,'w',encoding='utf-8') as f:
    f.write('VALIDACIÓN PORTICO R2\n=====================\n')
    f.write('FreeCAD: %s\n'%str(App.Version())); f.write('Objetos sólidos válidos: %d\n'%len(valid)); f.write('Nulos: %d\n'%len(null)); f.write('Inválidos: %d\n'%len(invalid)); f.write('Reimportación STEP: %s\n'%step_check); f.write('Mallas: %s\n'%'; '.join(mesh_status))
    for p in (OUT_FCSTD,OUT_STEP,OUT_STP,OUT_IGES,OUT_IGS,OUT_BREP,OUT_STL,OUT_OBJ,OUT_PLY,OUT_OFF,OUT_3MF): f.write('%s: %s\n'%(os.path.basename(p),os.path.getsize(p) if os.path.exists(p) else 'NO GENERADO'))
print('OK PORTICO R2'); print('OBJETOS',len(valid)); print('STEP_CHECK',step_check); print('OUT',OUT_DIR)
