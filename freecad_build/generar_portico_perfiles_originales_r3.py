# -*- coding: utf-8 -*-
"""Pórtico R3 construido sobre los sólidos exactos de Portico Avance.stp.

Los cuatro miembros del STEP fuente se copian sin cambiar forma, dimensiones ni posición.
Las dos vigas de agua se derivan de la geometría real de la viga superior del STEP;
solo se aplica el cambio dimensional solicitado para la cubierta (200 x 300 mm) y su
orientación a dos aguas. Las placas y pernos son editables y conceptuales.
"""
import os
import math
import hashlib
import shutil
import FreeCAD as App
import Part
import Import
import Mesh
import MeshPart

V = App.Vector
HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.environ.get("PORTICO_SOURCE", os.path.join(HERE, "Portico_Avance.stp"))
OUT = os.environ.get("PORTICO_OUT", os.path.join(HERE, "salida_portico_r3"))
os.makedirs(OUT, exist_ok=True)
BASE = "Portico_Dos_Aguas_Perfiles_Originales_R3"
path = lambda ext: os.path.join(OUT, BASE + ext)

EXPECTED_SOURCE_SHA256 = "4d074a678da4e83332e7f613f03165f157cd46f211ac922f42238e203827a183"
STEEL = (0.68, 0.71, 0.76)
ROOF = (0.57, 0.64, 0.75)
PLATE = (0.42, 0.47, 0.55)
BOLT = (0.22, 0.24, 0.28)
GUSSET = (0.50, 0.55, 0.62)


def sha256_file(filename):
    h = hashlib.sha256()
    with open(filename, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def unit(vec):
    q = V(vec.x, vec.y, vec.z)
    if q.Length < 1e-9:
        raise ValueError("Vector nulo")
    q.normalize()
    return q


def addv(a, b):
    return V(a.x + b.x, a.y + b.y, a.z + b.z)


def subv(a, b):
    return V(a.x - b.x, a.y - b.y, a.z - b.z)


def mulv(a, k):
    return V(a.x * k, a.y * k, a.z * k)


def set_color(obj, color):
    try:
        obj.ViewObject.ShapeColor = color
        obj.ViewObject.LineColor = (0.10, 0.10, 0.10)
        obj.ViewObject.DisplayMode = "Flat Lines"
    except Exception:
        pass


def add_feature(doc, group, name, label, shape, color=PLATE, description=""):
    if shape is None or shape.isNull():
        raise ValueError("Forma nula: " + name)
    obj = doc.addObject("Part::Feature", name)
    obj.Label = label
    obj.Shape = shape
    obj.addProperty("App::PropertyString", "Revision", "Proyecto")
    obj.Revision = "R3"
    obj.addProperty("App::PropertyString", "Descripcion", "Proyecto")
    obj.Descripcion = description
    if group is not None:
        group.addObject(obj)
    set_color(obj, color)
    return obj


def matrix_basis(ex, ey, ez, origin=None, sx=1.0, sy=1.0, sz=1.0):
    ex, ey, ez = unit(ex), unit(ey), unit(ez)
    o = origin or V(0, 0, 0)
    m = App.Matrix()
    m.A11, m.A12, m.A13, m.A14 = ex.x * sx, ey.x * sy, ez.x * sz, o.x
    m.A21, m.A22, m.A23, m.A24 = ex.y * sx, ey.y * sy, ez.y * sz, o.y
    m.A31, m.A32, m.A33, m.A34 = ex.z * sx, ey.z * sy, ez.z * sz, o.z
    m.A41, m.A42, m.A43, m.A44 = 0.0, 0.0, 0.0, 1.0
    return m


def oriented_box(width, length, thickness, center, ex, ey, ez):
    local = Part.makeBox(width, length, thickness, V(-width / 2.0, -length / 2.0, -thickness / 2.0))
    return local.transformGeometry(matrix_basis(ex, ey, ez, center))


def point(base, ey, ez, dy=0.0, dz=0.0, dx=0.0):
    return addv(addv(addv(base, mulv(ey, dy)), mulv(ez, dz)), V(dx, 0, 0))


def cylinder_between(p1, p2, radius):
    vec = subv(p2, p1)
    if vec.Length < 1e-8:
        raise ValueError("Cilindro de longitud nula")
    return Part.makeCylinder(radius, vec.Length, p1, unit(vec))


def bolt_shape(center, axis, span=100.0, diameter=20.0, washer=38.0, head=10.0):
    axis = unit(axis)
    p1 = subv(center, mulv(axis, span / 2.0))
    p2 = addv(center, mulv(axis, span / 2.0))
    shaft = cylinder_between(p1, p2, diameter / 2.0)
    h1 = Part.makeCylinder(washer / 2.0, head, subv(p1, mulv(axis, head)), axis)
    h2 = Part.makeCylinder(washer / 2.0, head, p2, axis)
    return Part.makeCompound([shaft, h1, h2])


def add_bolt(doc, group, name, label, center, axis, span=100.0, diameter=20.0):
    return add_feature(doc, group, name, label, bolt_shape(center, axis, span, diameter), BOLT,
                       "Perno conceptual editable; verificar diámetro, calidad y pretensión.")


def plate_with_holes(width, length, thickness, center, ex, ey, ez, local_holes, hole_d=22.0):
    plate = oriented_box(width, length, thickness, center, ex, ey, ez)
    ez = unit(ez)
    for hx, hy in local_holes:
        hc = addv(addv(center, mulv(unit(ex), hx)), mulv(unit(ey), hy))
        cutter = Part.makeCylinder(hole_d / 2.0, thickness + 20.0,
                                   subv(hc, mulv(ez, thickness / 2.0 + 10.0)), ez)
        plate = plate.cut(cutter)
    return plate


def gusset_local(base, ex, ey, ez, x_center, thickness, local_points):
    ex, ey, ez = unit(ex), unit(ey), unit(ez)
    pts = []
    for dy, dz in local_points:
        pts.append(subv(point(base, ey, ez, dy, dz, x_center), mulv(ex, thickness / 2.0)))
    pts.append(pts[0])
    return Part.Face(Part.makePolygon(pts)).extrude(mulv(ex, thickness))


def shape_signature(shape):
    b = shape.BoundBox
    return {
        "volume": shape.Volume,
        "bbox": (b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax),
        "faces": len(shape.Faces),
        "edges": len(shape.Edges),
        "solids": len(shape.Solids),
    }


def signatures_equal(a, b, tol=1e-6):
    if a["faces"] != b["faces"] or a["edges"] != b["edges"] or a["solids"] != b["solids"]:
        return False
    if abs(a["volume"] - b["volume"]) > max(tol, abs(a["volume"]) * 1e-10):
        return False
    return all(abs(x - y) <= tol for x, y in zip(a["bbox"], b["bbox"]))


def extract_source_members(source_file):
    temp = App.newDocument("Fuente_Portico_Avance")
    Import.insert(source_file, temp.Name)
    temp.recompute()
    candidates = []
    for obj in temp.Objects:
        if hasattr(obj, "Shape") and not obj.Shape.isNull() and len(obj.Shape.Solids) == 4:
            b = obj.Shape.BoundBox
            if b.XLength < 1000 and b.YLength > 9000 and b.ZLength > 9000:
                candidates.append(obj)
    if not candidates:
        raise RuntimeError("No se encontró el conjunto superior de cuatro perfiles en el STEP original")
    top = max(candidates, key=lambda o: o.Shape.Volume)
    source_solids = [s.copy() for s in top.Shape.Solids]
    records = []
    for solid in source_solids:
        b = solid.BoundBox
        if b.ZLength > 9000 and b.YLength < 1000:
            label = "Columna_Izquierda" if b.YMin < 0 else "Columna_Derecha"
        elif b.YLength > 8000 and b.ZLength < 1000:
            label = "Viga_Horizontal_Inferior" if b.ZMin < 4000 else "Viga_Horizontal_Superior"
        else:
            raise RuntimeError("Sólido fuente no reconocido: %s" % str((b.XLength, b.YLength, b.ZLength)))
        records.append((label, solid, shape_signature(solid)))
    App.closeDocument(temp.Name)
    return records


def roof_shape_from_exact_beam(source_beam, target_u, target_n, inner_start, target_length,
                               target_depth=300.0):
    """Reutiliza la geometría real del perfil fuente, adaptada a 300 x 200."""
    sh = source_beam.copy()
    bb = sh.BoundBox
    cx = (bb.XMin + bb.XMax) / 2.0
    cz = (bb.ZMin + bb.ZMax) / 2.0
    sh.translate(V(-cx, -bb.YMin, -cz))
    ex = V(1, 0, 0)
    sy = target_length / bb.YLength
    sz = target_depth / bb.ZLength
    transformed = sh.transformGeometry(matrix_basis(ex, target_u, target_n, V(0, 0, 0), 1.0, sy, sz))
    transformed.translate(addv(inner_start, mulv(unit(target_n), target_depth / 2.0)))
    return transformed


source_sha = sha256_file(SOURCE)
if source_sha != EXPECTED_SOURCE_SHA256:
    raise RuntimeError("El STEP fuente no coincide con el archivo subido. SHA256=%s" % source_sha)
source_records = extract_source_members(SOURCE)
source_by_name = {name: shape for name, shape, sig in source_records}
source_sig = {name: sig for name, shape, sig in source_records}

left_col_bb = source_by_name["Columna_Izquierda"].BoundBox
right_col_bb = source_by_name["Columna_Derecha"].BoundBox
upper_bb = source_by_name["Viga_Horizontal_Superior"].BoundBox
Y_LEFT = (left_col_bb.YMin + left_col_bb.YMax) / 2.0
Y_RIGHT = (right_col_bb.YMin + right_col_bb.YMax) / 2.0
Y_CENTER = (Y_LEFT + Y_RIGHT) / 2.0
COLUMN_TOP = max(left_col_bb.ZMax, right_col_bb.ZMax)
UPPER_BEAM_TOP = upper_bb.ZMax
RIDGE_INNER_Z = UPPER_BEAM_TOP + 3235.0
RUN = (Y_RIGHT - Y_LEFT) / 2.0
RISE = RIDGE_INNER_Z - COLUMN_TOP
SLOPE_LENGTH = math.hypot(RUN, RISE)
ANGLE_DEG = math.degrees(math.atan2(RISE, RUN))
c = RUN / SLOPE_LENGTH
s = RISE / SLOPE_LENGTH
u_left = V(0, c, s)
n_left = V(0, -s, c)
u_right = V(0, -c, s)
n_right = V(0, s, c)
ex = V(1, 0, 0)
left_inner = V(0, Y_LEFT, COLUMN_TOP)
right_inner = V(0, Y_RIGHT, COLUMN_TOP)
ridge_inner = V(0, Y_CENTER, RIDGE_INNER_Z)
ROOF_DEPTH = 300.0
ROOF_WIDTH = upper_bb.XLength
CENTER_GAP = 10.0
roof_length = SLOPE_LENGTH - CENTER_GAP / 2.0

doc = App.newDocument("Portico_Dos_Aguas_Perfiles_Originales_R3")
doc.Label = "Pórtico dos aguas R3 - perfiles originales inalterados"
g_original = doc.addObject("App::Part", "Perfiles_Originales_Inalterados")
g_original.Label = "Perfiles originales del STEP — NO MODIFICAR"
g_roof = doc.addObject("App::Part", "Vigas_Dos_Aguas_Desde_Perfil_Original")
g_roof.Label = "Vigas de agua 300x200 derivadas del perfil real"
g_eaves = doc.addObject("App::Part", "Conexiones_Aleros")
g_eaves.Label = "Conexiones de alero editables"
g_ridge = doc.addObject("App::Part", "Conexion_Cumbrera")
g_ridge.Label = "Conexión central editable"

original_objects = []
for name, shape, signature in sorted(source_records, key=lambda r: r[0]):
    obj = add_feature(doc, g_original, name, name.replace("_", " "), shape.copy(), STEEL,
                      "Copia geométrica exacta del sólido contenido en Portico Avance.stp. No escalar ni sustituir.")
    obj.addProperty("App::PropertyBool", "PerfilInalterado", "Fuente")
    obj.PerfilInalterado = True
    obj.addProperty("App::PropertyString", "SHA256Fuente", "Fuente")
    obj.SHA256Fuente = source_sha
    original_objects.append(obj)

source_roof_profile = source_by_name["Viga_Horizontal_Superior"]
roof_left_shape = roof_shape_from_exact_beam(source_roof_profile, u_left, n_left, left_inner, roof_length, ROOF_DEPTH)
roof_right_shape = roof_shape_from_exact_beam(source_roof_profile, u_right, n_right, right_inner, roof_length, ROOF_DEPTH)
roof_left = add_feature(doc, g_roof, "Viga_Agua_Izquierda", "Viga de agua izquierda — perfil real 300x200",
                        roof_left_shape, ROOF,
                        "Geometría derivada del perfil exacto de la viga superior del STEP, adaptada a 300x200.")
roof_right = add_feature(doc, g_roof, "Viga_Agua_Derecha", "Viga de agua derecha — perfil real 300x200",
                         roof_right_shape, ROOF,
                         "Geometría derivada del perfil exacto de la viga superior del STEP, adaptada a 300x200.")
for obj in (roof_left, roof_right):
    obj.addProperty("App::PropertyString", "PerfilFuente", "Fuente")
    obj.PerfilFuente = "Viga_Horizontal_Superior de Portico Avance.stp"
    obj.addProperty("App::PropertyFloat", "AnchoNominal", "Dimensiones")
    obj.AnchoNominal = ROOF_WIDTH
    obj.addProperty("App::PropertyFloat", "AltoNominal", "Dimensiones")
    obj.AltoNominal = ROOF_DEPTH


def build_eave(side, base, u, n):
    group = doc.addObject("App::Part", "Alero_" + side)
    group.Label = "Alero " + side
    g_eaves.addObject(group)
    holes_top = [(x, y) for y in (-220, 130, 480) for x in (-180, 180)]
    top_center = point(base, u, n, 230, ROOF_DEPTH + 8)
    top_shape = plate_with_holes(520, 1050, 16, top_center, ex, u, n, holes_top, 22)
    add_feature(doc, group, "Placa_Superior_Alero_" + side, "Placa superior de alero " + side,
                top_shape, PLATE, "Placa extendida sobre columna y viga inclinada.")
    for idx, (hx, hy) in enumerate(holes_top, 1):
        add_bolt(doc, group, "Perno_Superior_%s_%02d" % (side, idx), "Perno superior M20",
                 addv(addv(top_center, mulv(ex, hx)), mulv(u, hy)), n, 105, 20)

    end_center = point(base, u, n, 70, 145)
    end_holes = [(x, z) for z in (-105, 105) for x in (-145, 145)]
    end_plate = oriented_box(470, 16, 390, end_center, ex, u, n)
    for hx, hz in end_holes:
        hc = addv(addv(end_center, mulv(ex, hx)), mulv(n, hz))
        end_plate = end_plate.cut(Part.makeCylinder(11, 46, subv(hc, mulv(u, 23)), u))
    add_feature(doc, group, "Placa_Testa_Alero_" + side, "Placa de testa de alero " + side,
                end_plate, PLATE, "Placa de testa transversal al eje de la viga de agua.")
    for idx, (hx, hz) in enumerate(end_holes, 1):
        hc = addv(addv(end_center, mulv(ex, hx)), mulv(n, hz))
        add_bolt(doc, group, "Perno_Testa_%s_%02d" % (side, idx), "Perno de testa M20", hc, u, 125, 20)

    seat_center = point(base, u, n, 270, -9)
    seat_holes = [(x, y) for y in (-155, 155) for x in (-130, 130)]
    seat_shape = plate_with_holes(480, 620, 18, seat_center, ex, u, n, seat_holes, 22)
    add_feature(doc, group, "Asiento_Inferior_Alero_" + side, "Asiento inferior de alero " + side,
                seat_shape, PLATE, "Asiento inferior empernado con cartelas dobles.")
    for idx, (hx, hy) in enumerate(seat_holes, 1):
        add_bolt(doc, group, "Perno_Asiento_%s_%02d" % (side, idx), "Perno de asiento M20",
                 addv(addv(seat_center, mulv(ex, hx)), mulv(u, hy)), n, 95, 20)

    y_face = base.y + (275 if side == "Izquierdo" else -275)
    add_feature(doc, group, "Respaldo_Columna_" + side, "Respaldo de columna " + side,
                Part.makeBox(500, 16, 350, V(-250, y_face - 8, COLUMN_TOP - 310)), PLATE,
                "Placa agregada; no modifica el sólido de la columna original.")
    for j, xcenter in enumerate((-165, 165), 1):
        gus = gusset_local(base, ex, u, n, xcenter, 12, [(10, -20), (340, -20), (10, -330)])
        add_feature(doc, group, "Cartela_Alero_%s_%d" % (side, j), "Cartela de alero " + side,
                    gus, GUSSET, "Cartela triangular bajo el asiento.")


build_eave("Izquierdo", left_inner, u_left, n_left)
build_eave("Derecho", right_inner, u_right, n_right)


def add_ridge_side(tag, u, n):
    top_center = point(ridge_inner, u, n, -350, ROOF_DEPTH + 8)
    top_holes = [(x, y) for y in (-250, 20, 290) for x in (-175, 175)]
    top = plate_with_holes(520, 820, 16, top_center, ex, u, n, top_holes, 22)
    add_feature(doc, g_ridge, "Cubrejunta_Superior_" + tag, "Cubrejunta superior " + tag,
                top, PLATE, "Cubrejunta inclinada de la unión central.")
    for idx, (hx, hy) in enumerate(top_holes, 1):
        add_bolt(doc, g_ridge, "Perno_Cubrejunta_%s_%02d" % (tag, idx), "Perno cumbrera M20",
                 addv(addv(top_center, mulv(ex, hx)), mulv(u, hy)), n, 105, 20)

    end_center = point(ridge_inner, u, n, -22, 145)
    end_holes = [(x, z) for z in (-100, 100) for x in (-145, 145)]
    end_plate = oriented_box(470, 16, 390, end_center, ex, u, n)
    for hx, hz in end_holes:
        hc = addv(addv(end_center, mulv(ex, hx)), mulv(n, hz))
        end_plate = end_plate.cut(Part.makeCylinder(11, 46, subv(hc, mulv(u, 23)), u))
    add_feature(doc, g_ridge, "Placa_Testa_Cumbrera_" + tag, "Placa de testa cumbrera " + tag,
                end_plate, PLATE, "Placa de testa en cada extremo de viga.")
    for idx, (hx, hz) in enumerate(end_holes, 1):
        hc = addv(addv(end_center, mulv(ex, hx)), mulv(n, hz))
        add_bolt(doc, g_ridge, "Perno_Testa_Cumbrera_%s_%02d" % (tag, idx), "Perno testa cumbrera M20",
                 hc, u, 125, 20)

    lower_center = point(ridge_inner, u, n, -310, -9)
    lower_holes = [(x, y) for y in (-175, 175) for x in (-130, 130)]
    lower = plate_with_holes(480, 700, 18, lower_center, ex, u, n, lower_holes, 22)
    add_feature(doc, g_ridge, "Asiento_Inferior_Cumbrera_" + tag, "Asiento inferior cumbrera " + tag,
                lower, PLATE, "Placa inferior de continuidad.")
    for idx, (hx, hy) in enumerate(lower_holes, 1):
        add_bolt(doc, g_ridge, "Perno_Asiento_Cumbrera_%s_%02d" % (tag, idx), "Perno asiento cumbrera M20",
                 addv(addv(lower_center, mulv(ex, hx)), mulv(u, hy)), n, 95, 20)


add_ridge_side("Izquierda", u_left, n_left)
add_ridge_side("Derecha", u_right, n_right)

central = Part.makeBox(480, 20, 430, V(-240, Y_CENTER - 10, RIDGE_INNER_Z - 80))
central_holes = [(x, z) for z in (20, 170, 320) for x in (-170, 170)]
for hx, hz in central_holes:
    central = central.cut(Part.makeCylinder(11, 60, V(hx, Y_CENTER - 30, RIDGE_INNER_Z - 80 + hz), V(0, 1, 0)))
add_feature(doc, g_ridge, "Placa_Central_Cumbrera", "Placa central de cumbrera", central, PLATE,
            "Placa central editable que enlaza las placas de testa.")
for idx, (hx, hz) in enumerate(central_holes, 1):
    add_bolt(doc, g_ridge, "Perno_Central_%02d" % idx, "Perno central M20",
             V(hx, Y_CENTER, RIDGE_INNER_Z - 80 + hz), V(0, 1, 0), 130, 20)

for j, xcenter in enumerate((-165, 165), 1):
    pts = [V(xcenter - 6, Y_CENTER - 420, RIDGE_INNER_Z - 15),
           V(xcenter - 6, Y_CENTER + 420, RIDGE_INNER_Z - 15),
           V(xcenter - 6, Y_CENTER, RIDGE_INNER_Z - 430),
           V(xcenter - 6, Y_CENTER - 420, RIDGE_INNER_Z - 15)]
    gus = Part.Face(Part.makePolygon(pts)).extrude(V(12, 0, 0))
    add_feature(doc, g_ridge, "Cartela_Central_%d" % j, "Cartela central de cumbrera", gus, GUSSET,
                "Cartela triangular inferior de la conexión central.")

params = doc.addObject("App::FeaturePython", "Parametros_Dimensionales")
params.Label = "Parámetros dimensionales conservados"
for prop, value in [("SeparacionEjesColumnas", Y_RIGHT - Y_LEFT), ("AlturaColumnas", COLUMN_TOP),
                    ("CotaSuperiorUltimaViga", UPPER_BEAM_TOP), ("CotaInteriorCumbrera", RIDGE_INNER_Z),
                    ("DiferenciaSolicitada", 3235.0), ("AnguloCubiertaGrados", ANGLE_DEG),
                    ("AnchoVigaAgua", ROOF_WIDTH), ("AltoVigaAgua", ROOF_DEPTH)]:
    params.addProperty("App::PropertyLength" if "Angulo" not in prop else "App::PropertyAngle", prop, "Cotas")
    setattr(params, prop, value)
params.addProperty("App::PropertyString", "SHA256Fuente", "Fuente")
params.SHA256Fuente = source_sha

doc.recompute()
validation_lines = ["VALIDACION PORTICO R3 - PERFILES ORIGINALES", "SOURCE_SHA256=%s" % source_sha,
                    "SOURCE_SHA256_EXPECTED=%s" % EXPECTED_SOURCE_SHA256,
                    "SOURCE_SHA_MATCH=%s" % (source_sha == EXPECTED_SOURCE_SHA256), ""]
all_originals_ok = True
for obj in original_objects:
    sig_final = shape_signature(obj.Shape)
    sig_src = source_sig[obj.Name]
    ok = signatures_equal(sig_src, sig_final)
    all_originals_ok = all_originals_ok and ok
    validation_lines.append("%s INALTERADO=%s" % (obj.Name, ok))
    validation_lines.append("  volumen_fuente=%.9f volumen_final=%.9f" % (sig_src["volume"], sig_final["volume"]))
    validation_lines.append("  bbox_fuente=%s" % (sig_src["bbox"],))
    validation_lines.append("  bbox_final=%s" % (sig_final["bbox"],))
    validation_lines.append("  faces=%d edges=%d solids=%d" % (sig_final["faces"], sig_final["edges"], sig_final["solids"]))
shape_objects = [o for o in doc.Objects if hasattr(o, "Shape") and not o.Shape.isNull() and len(o.Shape.Solids) > 0]
invalid = []
for o in shape_objects:
    try:
        if not o.Shape.isValid():
            invalid.append(o.Name)
    except Exception:
        invalid.append(o.Name + "(error_validacion)")
validation_lines.extend(["", "PERFILES_ORIGINALES_TODOS_INALTERADOS=%s" % all_originals_ok,
                         "OBJETOS_SOLIDOS=%d" % len(shape_objects), "OBJETOS_INVALIDOS=%d" % len(invalid),
                         "LISTA_INVALIDOS=%s" % ",".join(invalid),
                         "SEPARACION_EJES=%.6f" % (Y_RIGHT - Y_LEFT),
                         "ALTURA_COLUMNAS=%.6f" % COLUMN_TOP,
                         "COTA_SUPERIOR_ULTIMA_VIGA=%.6f" % UPPER_BEAM_TOP,
                         "COTA_INTERIOR_CUMBRERA=%.6f" % RIDGE_INNER_Z,
                         "DIFERENCIA=%.6f" % (RIDGE_INNER_Z - UPPER_BEAM_TOP),
                         "PENDIENTE_GRADOS=%.9f" % ANGLE_DEG,
                         "VIGAS_AGUA_ANCHO=%.6f" % ROOF_WIDTH, "VIGAS_AGUA_ALTO=%.6f" % ROOF_DEPTH])
if not all_originals_ok or invalid:
    raise RuntimeError("Falló validación: originales_ok=%s invalidos=%s" % (all_originals_ok, invalid))

doc.saveAs(path(".FCStd"))
export_objects = shape_objects
Import.export(export_objects, path(".step"))
shutil.copyfile(path(".step"), path(".stp"))
Import.export(export_objects, path(".iges"))
shutil.copyfile(path(".iges"), path(".igs"))
compound = Part.makeCompound([o.Shape for o in export_objects])
compound.exportBrep(path(".brep"))
mesh = MeshPart.meshFromShape(Shape=compound, LinearDeflection=2.0, AngularDeflection=0.35, Relative=False)
mesh.write(path(".stl"))
mesh.write(path(".obj"))
with open(os.path.join(OUT, "Validacion_Portico_Perfiles_Originales_R3.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(validation_lines) + "\n")
with open(os.path.join(OUT, "Memoria_Dimensional_Portico_R3.txt"), "w", encoding="utf-8") as f:
    f.write("PÓRTICO DOS AGUAS R3\n")
    f.write("Los cuatro perfiles del archivo Portico Avance.stp se conservaron sin cambios.\n")
    f.write("SHA256 fuente: %s\n" % source_sha)
    f.write("Separación ejes columnas: %.3f mm\n" % (Y_RIGHT - Y_LEFT))
    f.write("Altura columnas: %.3f mm\n" % COLUMN_TOP)
    f.write("Última viga, cara superior: %.3f mm\n" % UPPER_BEAM_TOP)
    f.write("Punto interior cumbrera: %.3f mm\n" % RIDGE_INNER_Z)
    f.write("Diferencia vertical: %.3f mm\n" % (RIDGE_INNER_Z - UPPER_BEAM_TOP))
    f.write("Vigas de agua: perfil derivado de la geometría real, %.3f x %.3f mm\n" % (ROOF_DEPTH, ROOF_WIDTH))
    f.write("Pendiente: %.9f grados\n" % ANGLE_DEG)
    f.write("Placas, pernos y cartelas: geometría conceptual editable; verificar por cálculo.\n")
print("R3_COMPLETADO")
print("SOURCE_SHA256=" + source_sha)
print("ORIGINALES_INALTERADOS=" + str(all_originals_ok))
print("OBJETOS_SOLIDOS=" + str(len(shape_objects)))
print("PENDIENTE_GRADOS=%.9f" % ANGLE_DEG)
for ext in (".FCStd", ".step", ".stp", ".iges", ".igs", ".brep", ".stl", ".obj"):
    p = path(ext)
    print(os.path.basename(p), os.path.getsize(p))
