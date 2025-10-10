from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import random
import string
import mysql.connector
from datetime import datetime
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)  # Solo muestra errores, no las peticiones normales

# --- Conexión MySQL ---
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root",
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
clientes = {}       # sid -> {nombre: str, publicKey: str}
cliente_grp = {}    # sid -> clave del grupo actual o None
grupos_mem = {}     # clave -> {"nombre": nombre, "members": set(sid)}
public_keys = {}    # nombre_usuario -> clave_publica

# --- Función para generar claves ---
def generar_clave(longitud=6):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(longitud))

def log_crypto(evento, detalles):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"🔐 {evento}: {detalles}")

# --- Rutas ---
@app.route('/')
def index():
    return render_template('client.html')

# --- Conexión ---
@socketio.on('connect')
def handle_connect():
    log_crypto("Nueva conexión", request.sid)
    emit('server_message', "🟢 Conectado al servidor.")

# --- Nombre de usuario y clave pública ---
@socketio.on('set_name')
def handle_set_name(data):
    nombre = data.get('nombre', 'Anonimo')
    public_key = data.get('publicKey', '')
    sid = request.sid
    
    clientes[sid] = {
        'nombre': nombre,
        'publicKey': public_key
    }
    cliente_grp[sid] = None
    public_keys[nombre] = public_key

    log_crypto("Nuevo usuario", nombre)

    # Notificar solo a usuarios en global
    for other_sid, other_data in clientes.items():
        if other_sid != sid:
            # Enviar clave pública del nuevo usuario a usuarios existentes
            emit('user_public_key', {
                'user': nombre,
                'publicKey': public_key
            }, room=other_sid)
            
            # Enviar claves públicas de usuarios existentes al nuevo usuario
            if other_sid in clientes:
                emit('user_public_key', {
                    'user': clientes[other_sid]['nombre'],
                    'publicKey': clientes[other_sid]['publicKey']
                }, room=sid)
            
            if cliente_grp.get(other_sid) is None:
                socketio.emit('server_message', f"🔔 {nombre} se ha unido al chat global.", room=other_sid)

    emit('server_message', f"🟢 Conectado al servidor. Estás en chat global.", room=sid)

# --- Elegir / crear / unirse a grupo ---
@socketio.on('choose_group')
def handle_choose_group(data):
    instr = data.get('instr', '/nogroup')
    sid = request.sid
    nombre = clientes.get(sid, {}).get('nombre', "Anonimo")

    if instr.startswith("/create_group|"):
        grupo_nombre = instr.split("|",1)[1].strip() or "Grupo"
        clave = generar_clave()
        while True:
            cursor.execute("SELECT id FROM grupos WHERE clave=%s", (clave,))
            if cursor.fetchone() is None:
                break
            clave = generar_clave()
        
        cursor.execute("INSERT INTO grupos (clave, nombre) VALUES (%s,%s)", (clave, grupo_nombre))
        db.commit()
        cursor.execute("SELECT id FROM grupos WHERE clave=%s", (clave,))
        grupo_id = cursor.fetchone()['id']
        cursor.execute("INSERT INTO grupo_miembros (grupo_id, cliente_nombre) VALUES (%s,%s)", (grupo_id, nombre))
        db.commit()
        
        grupos_mem[clave] = {"nombre": grupo_nombre, "members": set([sid])}
        cliente_grp[sid] = clave
        
        log_crypto("Grupo creado", f"{nombre} -> {grupo_nombre}")
        emit('server_message', f"✅ Grupo creado: {grupo_nombre} | Clave: {clave}", room=sid)

    elif instr.startswith("/join_group|"):
        clave = instr.split("|",1)[1].strip()
        if clave in grupos_mem:
            grupos_mem[clave]["members"].add(sid)
            cliente_grp[sid] = clave
            
            log_crypto("Unión a grupo", f"{nombre} -> {grupos_mem[clave]['nombre']}")
            
            # Compartir claves públicas entre miembros del grupo
            for member_sid in grupos_mem[clave]["members"]:
                if member_sid != sid and member_sid in clientes:
                    emit('user_public_key', {
                        'user': nombre,
                        'publicKey': clientes[sid]['publicKey']
                    }, room=member_sid)
                    emit('user_public_key', {
                        'user': clientes[member_sid]['nombre'],
                        'publicKey': clientes[member_sid]['publicKey']
                    }, room=sid)
            
            emit('server_message', f"✅ Te uniste al grupo: {grupos_mem[clave]['nombre']} | Clave: {clave}", room=sid)
        else:
            log_crypto("Error unión a grupo", f"{nombre} -> clave inválida: {clave}")
            emit('server_message', f"❌ Clave inválida: {clave}. Estás en el chat global.", room=sid)
            cliente_grp[sid] = None
    else:
        cliente_grp[sid] = None

# --- Obtener lista de destinatarios ---
@socketio.on('get_recipients')
def handle_get_recipients(data):
    sid = request.sid
    nombre = clientes.get(sid, {}).get('nombre', "Anonimo")
    clave_usuario = cliente_grp.get(sid, None)
    
    recipients = []
    
    if clave_usuario and clave_usuario in grupos_mem:
        for member_sid in grupos_mem[clave_usuario]["members"]:
            if member_sid != sid and member_sid in clientes:
                recipients.append(clientes[member_sid]['nombre'])
    else:
        for other_sid, other_data in clientes.items():
            if other_sid != sid and cliente_grp.get(other_sid) is None:
                recipients.append(other_data['nombre'])
    
    emit('recipients_list', recipients, room=sid)

# --- Mensajes cifrados ---
@socketio.on('encrypted_message')
def handle_encrypted_message(data):
    sid = request.sid
    nombre = clientes.get(sid, {}).get('nombre', "Anonimo")
    encrypted_messages = data.get('encryptedMessages', {})
    
    log_crypto("Mensaje cifrado", f"De {nombre} para {len(encrypted_messages)} personas")
    
    for recipient_name, encrypted_msg in encrypted_messages.items():
        recipient_sid = None
        for target_sid, target_data in clientes.items():
            if target_data.get('nombre') == recipient_name:
                recipient_sid = target_sid
                break
        
        if recipient_sid:
            # Mostrar el mensaje cifrado en el log del servidor
            print(f"   📄 Mensaje cifrado (primeros 100 chars):")
            print(f"   {encrypted_msg[:100]}...")
            
            emit('server_message', {
                'encrypted': True,
                'message': encrypted_msg,
                'sender': nombre
            }, room=recipient_sid)
            log_crypto("Entregado a", recipient_name)


# --- Mensajes normales (para comandos) ---
@socketio.on('message')
def handle_message(msg):
    sid = request.sid
    nombre = clientes.get(sid, {}).get('nombre', "Anonimo")
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

# --- Desconexión ---
@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    cliente_data = clientes.pop(sid, {})
    nombre = cliente_data.get('nombre', "Anonimo")
    clave = cliente_grp.pop(sid, None)
    
    if nombre in public_keys:
        del public_keys[nombre]
    
    log_crypto("Usuario desconectado", nombre)
    
    if clave and clave in grupos_mem:
        grupos_mem[clave]["members"].discard(sid)
        if not grupos_mem[clave]["members"]:
            del grupos_mem[clave]

# --- Ejecutar ---
if __name__ == "__main__":
    print("🔐 Servidor con cifrado RSA iniciado")
    socketio.run(app, host="0.0.0.0", port=5555)