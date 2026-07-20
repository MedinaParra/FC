# -*- coding: utf-8 -*-
import os
import FreeCAD as App
import Import
src=os.environ['PORTICO_SOURCE']
out=os.environ['PORTICO_OUT']
os.makedirs(out,exist_ok=True)
doc=App.newDocument('Inspeccion_Portico_Original')
Import.insert(src,doc.Name)
doc.recompute()
lines=[]
lines.append('SOURCE='+src)
lines.append('OBJECTS=%d'%len(doc.Objects))
for oi,o in enumerate(doc.Objects):
    if not hasattr(o,'Shape') or o.Shape.isNull():
        lines.append('OBJ %03d %s %s NO_SHAPE'%(oi,o.Name,o.Label)); continue
    sh=o.Shape; bb=sh.BoundBox
    lines.append('OBJ %03d name=%s label=%s type=%s solids=%d volume=%.6f bbox=(%.6f,%.6f,%.6f) min=(%.6f,%.6f,%.6f) max=(%.6f,%.6f,%.6f)'%(oi,o.Name,o.Label,sh.ShapeType,len(sh.Solids),sh.Volume,bb.XLength,bb.YLength,bb.ZLength,bb.XMin,bb.YMin,bb.ZMin,bb.XMax,bb.YMax,bb.ZMax))
    for si,s in enumerate(sh.Solids):
        b=s.BoundBox
        lines.append('  SOLID %03d.%03d volume=%.6f bbox=(%.6f,%.6f,%.6f) min=(%.6f,%.6f,%.6f) max=(%.6f,%.6f,%.6f) faces=%d edges=%d'%(oi,si,s.Volume,b.XLength,b.YLength,b.ZLength,b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax,len(s.Faces),len(s.Edges)))
open(os.path.join(out,'Inspeccion_Portico_Original.txt'),'w').write('\n'.join(lines)+'\n')
doc.saveAs(os.path.join(out,'Portico_Avance_Importado.FCStd'))
print('\n'.join(lines))
