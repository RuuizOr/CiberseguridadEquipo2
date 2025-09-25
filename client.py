# client.py
# Cliente de chat con opción de crear/unirse a grupos al conectarse.
# Protocolo al conectar:
# 1) enviar nombre
# 2) enviar una instrucción de grupo:
#    /nogroup
#    /create_group|NombreGrupo
#    /join_group|CLAVE
# Luego ya se envían mensajes normales o comandos en caliente:
#    /create_group|Nombre
#    /join_group|CLAVE
#    /leave_group
#    /list_groups

import sys
import socket
import threading
import traceback

# Forzar UTF-8 en stdin/stdout/stderr si es posible (Python 3.7+)
try:
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

HOST = "127.0.0.1"  # cambiar por IP del servidor si es otra máquina
PORT = 5000

cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

def recibir():
    try:
        while True:
            data = cliente.recv(4096)
            if not data:
                print("❌ Conexión cerrada por el servidor")
                break
            try:
                msg = data.decode('utf-8')
            except UnicodeDecodeError:
                msg = data.decode('utf-8', errors='replace')
            print(msg)
    except Exception as e:
        print("Error en recepción:", e)
        traceback.print_exc()
    finally:
        try:
            cliente.close()
        except:
            pass

def elegir_opcion_grupo():
    print("\nOpciones para grupos:")
    print("  1) No entrar a grupo (chat global)")
    print("  2) Crear un grupo (te devolverá una clave)")
    print("  3) Unirte a un grupo con clave")
    opt = input("Elige 1, 2 o 3: ").strip()
    if opt == "1":
        return "/nogroup"
    if opt == "2":
        nombre = input("Nombre del nuevo grupo: ").strip()
        if not nombre:
            nombre = "Grupo"
        return f"/create_group|{nombre}"
    if opt == "3":
        clave = input("Introduce la clave del grupo: ").strip().upper()
        return f"/join_group|{clave}"
    # fallback
    return "/nogroup"

def main():
    nombre = input("Escribe tu nombre para el chat: ").strip()
    if not nombre:
        nombre = "Anonimo"

    # Conectar
    try:
        cliente.connect((HOST, PORT))
    except Exception as e:
        print("No se pudo conectar al servidor:", e)
        return

    # 1) enviar nombre
    try:
        cliente.sendall(nombre.encode('utf-8'))
    except Exception as e:
        print("Error enviando nombre:", e)
        cliente.close()
        return

    # 2) elegir opción de grupo y enviar la instrucción
    instr = elegir_opcion_grupo()
    try:
        cliente.sendall(instr.encode('utf-8'))
    except Exception as e:
        print("Error enviando instrucción de grupo:", e)
        cliente.close()
        return

    # iniciar hilo receptor
    hilo = threading.Thread(target=recibir, daemon=True)
    hilo.start()

    print("\n😎 Conectado. Usa emojis si quieres. Comandos útiles en caliente:")
    print("  /create_group|Nombre   -> crea un grupo y te une (recibirás la clave)")
    print("  /join_group|CLAVE      -> unirte a grupo existente")
    print("  /leave_group           -> salir del grupo (volver al global)")
    print("  /list_groups           -> pedir lista de grupos activos")
    print("  escribir 'salir'       -> desconectarte\n")

    try:
        while True:
            msg = input("👉 Tú: ")
            if msg.strip().lower() == "salir":
                print("👋 Saliendo...")
                break
            try:
                cliente.sendall(msg.encode('utf-8'))
            except Exception as e:
                print("No se pudo enviar el mensaje:", e)
                break
    except KeyboardInterrupt:
        print("\n👋 Interrumpido por teclado, saliendo...")
    finally:
        try:
            cliente.close()
        except:
            pass

if __name__ == "__main__":
    main()
