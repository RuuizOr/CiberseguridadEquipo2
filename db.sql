create database chat;

CREATE TABLE grupos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    clave VARCHAR(6) UNIQUE NOT NULL,
    nombre VARCHAR(255) NOT NULL
);

CREATE TABLE grupo_miembros (
    id INT AUTO_INCREMENT PRIMARY KEY,
    grupo_id INT NOT NULL,
    cliente_nombre VARCHAR(255) NOT NULL,
    FOREIGN KEY (grupo_id) REFERENCES grupos(id) ON DELETE CASCADE
);