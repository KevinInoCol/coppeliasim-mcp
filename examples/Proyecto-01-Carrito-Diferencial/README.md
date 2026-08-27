# Proyecto 01 — Carrito diferencial

Un carrito de tracción diferencial que detecta un obstáculo con un sensor de
proximidad y frena antes de chocar.

Los dos scripts son **dos etapas del mismo proyecto**, no dos versiones a elegir.
Se escribieron en este orden y se leen en este orden.

## 1. `carrito_con_sensor.py` — la etapa exploratoria

**No construye el carrito: lo encuentra.** Parte de un carrito montado a mano
con las tools del MCP, que crea primitivas sueltas y sin jerarquía. El script
recorre la escena buscando una forma que mida 0.4 x 0.25 x 0.06 y adopta como
piezas del carrito todo lo que esté a menos de 0.35 m. Después las emparenta al
chasis, le cuelga un sensor cónico en el morro, pone un cubo delante y demuestra
el frenado.

Es frágil a propósito, y por eso está aquí: enseña por qué montar geometría a
mano no escala, que es lo que motivó la etapa siguiente.

```
python Proyecto-01-Carrito-Diferencial/carrito_con_sensor.py
python Proyecto-01-Carrito-Diferencial/carrito_con_sensor.py --solo-montar
```

Requiere un carrito ya presente en la escena.

## 2. `carrito_diferencial.py` — la etapa definitiva

Construye **todo** por código: chasis, dos ruedas motrices con juntas de verdad,
rueda loca, sensor, recinto y obstáculo. Luego lo prueba durante 45 segundos y
publica un informe con la distancia recorrida frente a la teórica.

No necesita nada previo en la escena y se puede ejecutar tantas veces como
quieras: `limpiar()` borra lo de la corrida anterior.

```
python Proyecto-01-Carrito-Diferencial/carrito_diferencial.py
python Proyecto-01-Carrito-Diferencial/carrito_diferencial.py --solo-construir
```

## Qué salió de aquí

Este proyecto produjo dos hallazgos que acabaron documentados en el servidor MCP
y en sus skills:

- **Bullet 2.7 obedece `bullet.frictionOld`, no `bullet.friction`.** Escribir
  solo la nueva no hace nada, sin error ni aviso. Medido: con la rueda loca mal,
  el carrito recorría el 87% de su distancia en recta y el 51% en giro. Con las
  dos propiedades escritas, 99% y 99%.
- **Un cono ancho en horizontal ve el suelo antes que el obstáculo.** Con
  semiapertura *a* y el sensor a altura *h*, el suelo entra en el cono a
  *h / tan(a)*.

## Escena

`Escena_Carrito_Evade_Obstaculos.ttt` es el resultado guardado de la etapa 1.
