# server.py
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import random
import string
import mysql.connector

# --- Conexión MySQL ---
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="chat"
)
cursor = db.cursor(dictionary=True)

try:
    db.ping(reconnect=True)
    print("Conexión OK")
except Exception as e:
    print("Error de DB:", e)

# --- Flask + SocketIO ---
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- Memoria ---
clientes = {}       # sid -> nombre
cliente_grp = {}    # sid -> clave del grupo actual o None
grupos_mem = {}     # clave -> {"nombre": nombre, "members": set(sid)}

# --- Función para generar claves ---
def generar_clave(longitud=6):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(longitud))

# --- Rutas ---
@app.route('/')
def index():
    return render_template('client.html')

# --- Conexión ---
@socketio.on('connect')
def handle_connect():
    emit('server_message', "🟢 Conectado al servidor.")

# --- Nombre de usuario ---
@socketio.on('set_name')
def handle_set_name(data):
    nombre = data.get('nombre', 'Anonimo')
    clientes[request.sid] = nombre
    cliente_grp[request.sid] = None

    # Notificar solo a usuarios en global
    for sid2, grp in cliente_grp.items():
        if grp is None and sid2 != request.sid:
            socketio.emit('server_message', f"🔔 {nombre} se ha unido al chat global.", room=sid2)

    emit('server_message', f"🟢 Conectado al servidor. Estás en chat global.", room=request.sid)
    print(f"[CONEXIÓN] {nombre} se ha unido al chat global.")

# --- Elegir / crear / unirse a grupo ---
@socketio.on('choose_group')
def handle_choose_group(data):
    instr = data.get('instr', '/nogroup')
    sid = request.sid
    nombre = clientes.get(sid, "Anonimo")

    if instr.startswith("/create_group|"):
        grupo_nombre = instr.split("|",1)[1].strip() or "Grupo"
        # Generar clave única
        clave = generar_clave()
        while True:
            cursor.execute("SELECT id FROM grupos WHERE clave=%s", (clave,))
            if cursor.fetchone() is None:
                break
            clave = generar_clave()
        # Guardar grupo en DB
        cursor.execute("INSERT INTO grupos (clave, nombre) VALUES (%s,%s)", (clave, grupo_nombre))
        db.commit()
        cursor.execute("SELECT id FROM grupos WHERE clave=%s", (clave,))
        grupo_id = cursor.fetchone()['id']
        # Guardar al creador como miembro
        cursor.execute("INSERT INTO grupo_miembros (grupo_id, cliente_nombre) VALUES (%s,%s)", (grupo_id, nombre))
        db.commit()
        # Guardar en memoria
        grupos_mem[clave] = {"nombre": grupo_nombre, "members": set([sid])}
        cliente_grp[sid] = clave
        print(f"[GRUPO] {nombre} creó el grupo '{grupo_nombre}' ({clave})")

        # Solo el creador recibe la clave
        emit('server_message', f"✅ Grupo creado: {grupo_nombre} | Clave: {clave}", room=sid)
        # Notificación global sin clave
        for other_sid, other_clave in cliente_grp.items():
            if other_clave is None and other_sid != sid:
                socketio.emit('server_message', f"🔔 {nombre} ha creado un nuevo grupo.", room=other_sid)

    elif instr.startswith("/join_group|"):
        clave = instr.split("|",1)[1].strip()
        if clave in grupos_mem:
            grupos_mem[clave]["members"].add(sid)
            cliente_grp[sid] = clave
            # Solo usuario que se une recibe confirmación con clave
            emit('server_message', f"✅ Te uniste al grupo: {grupos_mem[clave]['nombre']} | Clave: {clave}", room=sid)
            # Notificación solo a miembros del grupo
            for member_sid in grupos_mem[clave]["members"]:
                if member_sid != sid:
                    socketio.emit('server_message', f"🔔 {nombre} se ha unido al grupo '{grupos_mem[clave]['nombre']}'", room=member_sid)
        else:
            emit('server_message', f"❌ Clave inválida: {clave}. Estás en el chat global.", room=sid)
            cliente_grp[sid] = None
    else:
        cliente_grp[sid] = None

# --- Mensajes ---
@socketio.on('message')
def handle_message(msg):
    sid = request.sid
    nombre = clientes.get(sid, "Anonimo")
    clave_usuario = cliente_grp.get(sid, None)
    texto = msg.strip()

    # Comandos
    if texto.startswith("/"):
        cmd = texto.strip()
        if cmd == "/leave_group":
            clave_act = cliente_grp.get(sid)
            if clave_act and clave_act in grupos_mem:
                g = grupos_mem[clave_act]
                if sid in g["members"]:
                    g["members"].remove(sid)
                    cliente_grp[sid] = None
                    emit('server_message', f"✅ Has salido del grupo '{g['nombre']}'", room=sid)
                    for member_sid in g["members"]:
                        socketio.emit('server_message', f"🔔 {nombre} ha salido del grupo '{g['nombre']}'", room=member_sid)
                    if not g["members"]:
                        del grupos_mem[clave_act]
                else:
                    emit('server_message', "ℹ️ No estabas en ningún grupo.", room=sid)
            else:
                emit('server_message', "ℹ️ No estabas en ningún grupo.", room=sid)
            return

        if cmd == "/list_groups":
            if grupos_mem:
                resumen = "Grupos activos:\n" + "\n".join([f"- {v['nombre']} (Clave: {k}) Miembros: {len(v['members'])}" for k,v in grupos_mem.items()])
            else:
                resumen = "No hay grupos activos."
            emit('server_message', resumen, room=sid)
            return

        emit('server_message', "ℹ️ Comando no reconocido.", room=sid)
        return

    # Mensaje normal
    if clave_usuario and clave_usuario in grupos_mem:
        # Enviar SOLO a miembros del grupo
        for member_sid in grupos_mem[clave_usuario]["members"]:
            socketio.emit('server_message', f"{nombre} (grupo) 💬 {texto}", room=member_sid)
    else:
        # Enviar SOLO a usuarios global
        for other_sid, other_clave in cliente_grp.items():
            if other_clave is None:
                socketio.emit('server_message', f"{nombre} 💬 {texto}", room=other_sid)

# --- Desconexión ---
@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    nombre = clientes.pop(sid, "Anonimo")
    clave = cliente_grp.pop(sid, None)
    if clave and clave in grupos_mem:
        grupos_mem[clave]["members"].discard(sid)
        if not grupos_mem[clave]["members"]:
            del grupos_mem[clave]
        else:
            for member_sid in grupos_mem[clave]["members"]:
                socketio.emit('server_message', f"🔔 {nombre} se ha ido del grupo '{grupos_mem[clave]['nombre']}'", room=member_sid)
    # Solo se desconecta en global si estaba en global
    if clave is None:
        emit('server_message', f"🔴 Desconectado: {nombre}", room=sid)

# --- Ejecutar ---
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5555)
