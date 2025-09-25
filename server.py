# server.py
# Servidor Flask con SocketIO para chat con grupos y mensajes globales.

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import string

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

clientes = {}  # sid -> nombre
cliente_grp = {}  # sid -> grupo_key (None = global)
grupos = {}   # clave -> {"nombre": nombre, "members": set(sid)}

def generar_clave(longitud=6):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(longitud))

@app.route('/')
def index():
    return render_template('client.html')

@socketio.on('connect')
def handle_connect():
    emit('server_message', "🟢 Conectado al servidor.")

@socketio.on('set_name')
def handle_set_name(data):
    nombre = data.get('nombre', 'Anonimo')
    clientes[request.sid] = nombre
    cliente_grp[request.sid] = None
    emit('server_message', f"🔔 {nombre} se ha unido al chat global.", broadcast=True)

@socketio.on('choose_group')
def handle_choose_group(data):
    instr = data.get('instr', '/nogroup')
    sid = request.sid
    nombre = clientes.get(sid, "Anonimo")

    if instr.startswith("/create_group|"):
        grupo_nombre = instr.split("|", 1)[1].strip() or "Grupo"
        clave = generar_clave()
        while clave in grupos:
            clave = generar_clave()
        grupos[clave] = {"nombre": grupo_nombre, "members": set([sid])}
        cliente_grp[sid] = clave
        emit('server_message', f"✅ Grupo creado: {grupo_nombre} | Clave: {clave}")
        emit('server_message', f"🔔 {nombre} ha creado el grupo '{grupo_nombre}'. Clave: {clave}", broadcast=True)
    elif instr.startswith("/join_group|"):
        clave = instr.split("|", 1)[1].strip()
        if clave in grupos:
            grupos[clave]["members"].add(sid)
            cliente_grp[sid] = clave
            emit('server_message', f"✅ Te uniste al grupo: {grupos[clave]['nombre']} | Clave: {clave}")
            for member_sid in grupos[clave]["members"]:
                if member_sid != sid:
                    socketio.emit('server_message', f"🔔 {nombre} se ha unido al grupo '{grupos[clave]['nombre']}'", room=member_sid)
        else:
            emit('server_message', f"❌ Clave inválida: {clave}. Estás en el chat global.")
            cliente_grp[sid] = None
    else:
        # /nogroup o cualquier otra cosa
        cliente_grp[sid] = None

@socketio.on('message')
def handle_message(msg):
    sid = request.sid
    nombre = clientes.get(sid, "Anonimo")
    clave_usuario = cliente_grp.get(sid, None)
    texto = msg.strip()

    # Comandos en caliente
    if texto.startswith("/"):
        cmd = texto.strip()
        if cmd == "/leave_group":
            clave_act = cliente_grp.get(sid)
            if clave_act:
                g = grupos.get(clave_act)
                if g and sid in g["members"]:
                    g["members"].remove(sid)
                    cliente_grp[sid] = None
                    emit('server_message', f"✅ Has salido del grupo '{g['nombre']}'")
                    for member_sid in g["members"]:
                        socketio.emit('server_message', f"🔔 {nombre} ha salido del grupo '{g['nombre']}'", room=member_sid)
                    if not g["members"]:
                        del grupos[clave_act]
                else:
                    emit('server_message', "ℹ️ No estabas en ningún grupo.")
            else:
                emit('server_message', "ℹ️ No estabas en ningún grupo.")
            return

        if cmd.startswith("/create_group|"):
            grupo_nombre = cmd.split("|", 1)[1].strip() or "Grupo"
            clave = generar_clave()
            while clave in grupos:
                clave = generar_clave()
            grupos[clave] = {"nombre": grupo_nombre, "members": set([sid])}
            cliente_grp[sid] = clave
            emit('server_message', f"✅ Grupo creado: {grupo_nombre} | Clave: {clave}")
            emit('server_message', f"🔔 {nombre} ha creado el grupo '{grupo_nombre}'. Clave: {clave}", broadcast=True)
            return

        if cmd.startswith("/join_group|"):
            clave = cmd.split("|", 1)[1].strip()
            if clave in grupos:
                grupos[clave]["members"].add(sid)
                cliente_grp[sid] = clave
                emit('server_message', f"✅ Te uniste al grupo: {grupos[clave]['nombre']} | Clave: {clave}")
                for member_sid in grupos[clave]["members"]:
                    if member_sid != sid:
                        socketio.emit('server_message', f"🔔 {nombre} se ha unido al grupo '{grupos[clave]['nombre']}'", room=member_sid)
            else:
                emit('server_message', f"❌ Clave inválida: {clave}")
            return

        if cmd == "/list_groups":
            if grupos:
                resumen = "Grupos activos:\n" + "\n".join([f"- {v['nombre']} (Clave: {k}) Miembros: {len(v['members'])}" for k,v in grupos.items()])
            else:
                resumen = "No hay grupos activos."
            emit('server_message', resumen)
            return

        emit('server_message', "ℹ️ Comando no reconocido.")
        return

    # Mensaje normal
    if clave_usuario:
        # A miembros del grupo
        for member_sid in grupos[clave_usuario]["members"]:
            if member_sid != sid:
                socketio.emit('server_message', f"{nombre} (grupo) 💬 {texto}", room=member_sid)
    else:
        # Mensaje global
        emit('server_message', f"{nombre} 💬 {texto}", broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    nombre = clientes.pop(sid, "Anonimo")
    clave = cliente_grp.pop(sid, None)
    if clave and clave in grupos:
        grupos[clave]["members"].discard(sid)
        if not grupos[clave]["members"]:
            del grupos[clave]
        else:
            for member_sid in grupos[clave]["members"]:
                socketio.emit('server_message', f"🔔 {nombre} se ha ido del grupo '{grupos[clave]['nombre']}'", room=member_sid)
    emit('server_message', f"🔴 Desconectado: {nombre}", broadcast=True)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5555)