---
name: construir-escena
description: Construir escenas de CoppeliaSim por código — paredes con vanos, suelos, obstáculos, y las tres propiedades independientes (dinámico, respondable, detectable) que deciden si un objeto cae, choca o es visible para un sensor. Incluye cómo verificar por programa que un robot cabe y que todas las zonas son alcanzables. Úsala al crear o modificar la geometría de una escena.
---

# Construir una escena por código

## Las tres propiedades, y por qué se confunden

Un objeto de CoppeliaSim tiene tres interruptores **independientes**. Casi todos
los problemas de escena salen de confundirlos:

| Propiedad | Qué decide | Si está mal |
|---|---|---|
| `dynamic` | si la física lo mueve (cae, se empuja) | el decorado se derrumba al dar Play |
| `respondable` | si otros cuerpos chocan con él | el robot atraviesa las paredes |
| `detectable` | si un sensor de proximidad lo ve | el sensor "no funciona" |

Una pared de decorado es **no dinámica, respondable y detectable**:

```python
sim.setBoolProperty(handle, "dynamic", False)
sim.setBoolProperty(handle, "respondable", True)
sim.setObjectInt32Param(handle, sim.shapeintparam_respondable_mask, 0xFFFF)
sim.setBoolProperty(handle, "detectable", True)
```

**`detectable` es la causa número uno de "mi sensor no detecta nada".** No se
hereda ni se activa sola: un objeto recién creado es invisible para todo sensor
de proximidad hasta que se le pone.

## Los suelos decorativos no deben ser sólidos

Si pintas el suelo de cada habitación con una caja fina, esa caja **no** puede
ser respondable ni colisionable. Un suelo de 1 cm de grosor es un escalón de
1 cm en cada vano, y el robot tropieza con él o se queda clavado.

Déjalos como pura decoración: no dinámicos, no respondables, no detectables. El
robot rueda sobre el terreno de verdad, no sobre la capa de color.

## El suelo por defecto mide 5 x 5 m

`/Floor` viene con la escena y es pequeño para casi cualquier planta. Si tu
escena es mayor, bórralo y crea un terreno del tamaño que necesites, o el robot
se caerá por el borde a mitad de recorrido.

## Paredes con vanos

Una pared con puerta no es un objeto: son dos tramos con un hueco entre medias.
Genera los tramos a partir de la línea completa y la lista de vanos, en vez de
colocar cada trozo a mano — así los números salen de un sitio solo y mover una
puerta no obliga a recalcular nada:

```python
def tramos_de_muro(inicio, fin, puertas):
    """Devuelve los trozos de pared entre inicio y fin, saltando los vanos."""
```

Cotas que funcionan en la práctica: vanos de 0.90 m y pasillos de 1.20 m dejan
pasar y girar a un robot de unos 0.40 x 0.25 m. Comprueba la holgura, no la des
por supuesta.

## Nombres y jerarquía

Cuelga todo de una raíz con alias (`/Casa`, `/Robot`). Eso hace que `limpiar()`
sea una línea y que la escena se lea de un vistazo.

**Emparentar renumera los hermanos.** Después de colgar `/Cylinder[1]` de un
chasis, `/Cylinder[3]` puede pasar a llamarse `/Cylinder[1]`. Si haces varios
`emparentar` seguidos, vuelve a listar entre uno y otro, o resuelve todos los
handles antes de empezar. Un script que asume los nombres estables se rompe de
formas muy difíciles de leer.

## Verificar que la escena sirve

Construir no es terminar. Dos comprobaciones que valen su peso:

**1. Rasterizar y medir la holgura.** Proyecta las huellas de las paredes a una
rejilla y comprueba que queda hueco suficiente en cada vano para el radio de
giro del robot.

**2. Alcanzabilidad por BFS.** Desde la entrada, recorre la rejilla con una
cola y comprueba que se llega a todas las zonas. Es unas quince líneas y detecta
al instante la habitación que quedó tapiada por un error de un decímetro:

```python
from collections import deque

def alcanzables(rejilla, origen, partida):
    vistos, cola = {partida}, deque([partida])
    while cola:
        x, y = cola.popleft()
        for vecino in ((x+1,y), (x-1,y), (x,y+1), (x,y-1)):
            if libre(rejilla, vecino) and vecino not in vistos:
                vistos.add(vecino); cola.append(vecino)
    return vistos
```

Imprimir la rejilla como texto ASCII en la terminal es la forma más rápida de
ver qué pasó. Una vista cenital en caracteres revela un vano tapiado más rápido
que mirar la escena en 3D.

## Al final, y solo al final

Guarda la escena **después** de verificar. Guardar antes deja un `.ttt` roto que
parece bueno.
