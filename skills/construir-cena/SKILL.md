---
name: construir-cena
description: Construir cenas do CoppeliaSim por código — paredes com vãos, chãos, obstáculos, e as três propriedades independentes (dinâmico, respondable, detectável) que decidem se um objeto cai, colide ou é visível para um sensor. Inclui como verificar por programa que o robô passa e que todas as áreas são alcançáveis. Use ao criar ou alterar a geometria de uma cena.
---

# Construir uma cena por código

## As três propriedades, e por que se confundem

Um objeto do CoppeliaSim tem três chaves **independentes**. Quase todo problema
de cena vem de misturá-las:

| Propriedade | O que decide | Quando está errado |
|---|---|---|
| `dynamic` | se a física move (cai, é empurrado) | o cenário desaba no Play |
| `respondable` | se outros corpos colidem com ele | o robô atravessa as paredes |
| `detectable` | se um sensor de proximidade enxerga | o sensor "não funciona" |

Uma parede de cenário é **não dinâmica, respondable e detectável**:

```python
sim.setBoolProperty(handle, "dynamic", False)
sim.setBoolProperty(handle, "respondable", True)
sim.setObjectInt32Param(handle, sim.shapeintparam_respondable_mask, 0xFFFF)
sim.setBoolProperty(handle, "detectable", True)
```

**`detectable` é a causa número um de "meu sensor não detecta nada".** Não se
herda nem se ativa sozinha: um objeto recém-criado é invisível para todo sensor
de proximidade até você marcar.

## Chãos decorativos não podem ser sólidos

Se você pinta o chão de cada cômodo com uma caixa fina, essa caixa **não** pode
ser respondable nem colidível. Um chão de 1 cm é um degrau de 1 cm em cada vão, e
o robô tropeça nele ou trava.

Deixe como pura decoração: não dinâmicos, não respondables, não detectáveis. O
robô rola sobre o terreno de verdade, não sobre a camada de cor.

## O chão padrão tem 5 x 5 m

O `/Floor` vem com a cena e é pequeno para quase qualquer planta. Se sua cena for
maior, apague e crie um terreno do tamanho necessário, ou o robô vai cair da
borda no meio do percurso.

## Paredes com vãos

Uma parede com porta não é um objeto: são dois trechos com um buraco no meio.
Gere os trechos a partir da linha completa e da lista de vãos, em vez de colocar
cada pedaço na mão — assim os números saem de um lugar só e mover uma porta não
obriga a recalcular nada:

```python
def trechos_de_muro(inicio, fim, portas):
    """Devolve os pedaços de parede entre início e fim, pulando os vãos."""
```

Medidas que funcionam na prática: vãos de 0,90 m e corredores de 1,20 m deixam
passar e girar um robô de uns 0,40 x 0,25 m. Confira a folga, não suponha.

## Nomes e hierarquia

Pendure tudo numa raiz com alias (`/Casa`, `/Robo`). Isso faz o `limpar()` virar
uma linha e a cena ficar legível de relance.

**Reparentar renumera os irmãos.** Depois de pendurar `/Cylinder[1]` num chassi,
`/Cylinder[3]` pode virar `/Cylinder[1]`. Se você reparenta várias vezes
seguidas, liste de novo entre uma e outra, ou resolva todos os handles antes. Um
script que supõe nomes estáveis quebra de formas muito difíceis de ler.

## Verificar que a cena serve

Construir não é terminar. Duas conferências que valem o peso:

**1. Rasterizar e medir a folga.** Projete as pegadas das paredes numa grade e
confira que sobra espaço em cada vão para o raio de giro do robô.

**2. Alcançabilidade por BFS.** Da entrada, percorra a grade com uma fila e
confirme que se chega a todas as áreas. São umas quinze linhas e pega na hora o
cômodo que ficou murado por um erro de um decímetro:

```python
from collections import deque

def alcancaveis(grade, origem, partida):
    vistos, fila = {partida}, deque([partida])
    while fila:
        x, y = fila.popleft()
        for v in ((x+1,y), (x-1,y), (x,y+1), (x,y-1)):
            if livre(grade, v) and v not in vistos:
                vistos.add(v); fila.append(v)
    return vistos
```

Imprimir a grade como ASCII no terminal é o jeito mais rápido de ver o que
aconteceu. Uma vista de cima em caracteres revela um vão murado mais rápido do
que olhar a cena em 3D.

## No fim, e só no fim

Salve a cena **depois** de verificar. Salvar antes deixa um `.ttt` quebrado que
parece bom.
