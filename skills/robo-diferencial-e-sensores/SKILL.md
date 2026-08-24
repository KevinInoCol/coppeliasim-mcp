---
name: robo-diferencial-e-sensores
description: Montar um robô de tração diferencial no CoppeliaSim e fazer ele andar de verdade — o eixo e o modo de controle das juntas, o atrito que o Bullet obedece, massa e inércia, grupos de colisão — mais sensores de proximidade, a zona cega e por que um cone largo enxerga o chão. Use ao construir um robô móvel, ao montar rodas ou juntas, ou quando o robô não anda, treme, patina ou o sensor não detecta.
---

# Robô diferencial e sensores

Cada armadilha desta página custa horas. Todas foram medidas num robô que
funciona.

## Juntas: o eixo e o modo de controle

**Uma junta atua ao longo do próprio +Z.** Para uma roda que impulsiona para
+X, o eixo precisa ficar sobre Y, o que significa girar a junta inteira (`-pi/2`
em torno de X). Não é parâmetro da chamada: é a orientação do objeto.

**Uma junta sem modo de controle é surda.** Você manda velocidade e nada
acontece até definir `dynCtrlMode`, que é uma **propriedade**, não um argumento
da criação. No modo de velocidade o valor é 4 (não 2, que é o que se supõe):

```python
sim.setInt32Property(junta, "dynCtrlMode", sim.jointdynctrl_velocity)
sim.setJointTargetVelocity(junta, 3.0)
```

A tool `crear_junta` do MCP faz as duas coisas por você.

## Atrito: o Bullet lê `frictionOld`

**O Bullet 2.7, que é o motor padrão, obedece `bullet.frictionOld`, não
`bullet.friction`.** O CoppeliaSim expõe os dois e qual manda depende da versão
do Bullet escolhida na cena. Definir só `bullet.friction` não faz absolutamente
nada.

Medido num diferencial real: uma roda boba com o atrito velho em 1 arrastou o
robô para **87% da distância** em reta e **51% do giro**, patinando em vez de
pivotar sobre o eixo motriz. Escreva sempre os dois.

Roda boba: atrito bem baixo. Rodas motrizes: atrito alto.

## Massa e inércia

`computeMassAndInertia` **só funciona com formas convexas**. Não funda o chassi
com a carga e depois chame: deixe cada peça convexa separada e calcule a massa
de cada uma.

Sem massa razoável, um robô leve com rodas finas treme ou sai voando.

## Rodas finas

Rodas de 1 cm de espessura são pouquíssimo para o Bullet: o contato é quase uma
linha e o robô treme. Compense com atrito alto e massa suficiente. Se o robô
vibra parado, trace a altura do chassi ao longo do tempo — se oscila, é isso.

## Grupos de colisão

As peças do robô não devem colidir entre si, mas devem colidir com o mundo. A
máscara de respondable resolve as duas coisas: os 8 bits baixos dizem com quem
colide dentro da mesma árvore e os 8 altos com o resto. Com `0xFF00` as peças do
robô se ignoram — acabaram os tremores — e continuam batendo no chão e nos
obstáculos.

## Reparentar não é unir

**Pendurar uma forma dinâmica em outra não une as duas rigidamente.** Ela cai do
mesmo jeito, e o robô se desmonta no Play. Para unir dois corpos dinâmicos é
preciso uma junta ou um sensor de força, que é o que a tool `crear_union_rigida`
faz.

## Sensores de proximidade

**O objeto precisa ser `detectable`.** É a razão habitual de um sensor "não
funcionar". Veja a skill de construir cenas.

**Ler não é detectar.** `sim.readProximitySensor` devolve o resultado da última
passada do simulador, então **com a simulação parada sempre diz que não há
nada**. Para detectar sob demanda use `sim.checkProximitySensor` (a
`comprobar_sensor_proximidad` do MCP).

**O `offset` é zona cega de verdade.** Um Sharp infravermelho com alcance de 10 a
80 cm não enxerga nada mais perto que 10 cm, e modelar isso com o offset
reproduz exatamente esse comportamento. Um obstáculo colado no nariz é
invisível: não é bug.

**Um cone largo apontando na horizontal enxerga o chão.** Com semiabertura *a* e
o sensor na altura *h*, o chão entra no cone a *h / tan(a)*. Se isso for menor
que o alcance, o sensor reporta o chão o tempo todo e parece quebrado. Confira o
número antes de culpar o sensor:

```python
def distancia_ao_chao(altura, abertura):
    return altura / math.tan(abertura)
```

Com 10° de abertura e o sensor a 10 cm, o chão aparece a 57 cm. Com 45°, a
10 cm: inútil.

## Testar o robô

Não suponha que anda. Meça:

- **Sensor**: ponha um obstáculo a três distâncias conhecidas, uma dentro da
  zona cega, e confira as três leituras.
- **Reta**: mesma velocidade nas duas rodas, trace a posição e compare a
  distância percorrida com a teórica (`raio * omega * tempo`). Abaixo de 90% há
  patinação: olhe o atrito.
- **Giro**: velocidades opostas e acumule o ângulo. Se patina em vez de pivotar,
  a roda boba tem atrito demais.
- **Estabilidade**: trace a altura do chassi. Se oscila, é massa ou rodas finas.

## Tempo real

Para teleoperar, ligue o modo de tempo real. Sem ele a simulação roda o mais
rápido que consegue: mediu-se **49 segundos simulados em 2 segundos de
relógio**, e não há reflexo humano que dê conta.
