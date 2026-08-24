---
name: estrutura-de-projeto
description: Como organizar um projeto de robótica no CoppeliaSim para que seja reprodutível — um script por artefato, a ordem conectar/limpar/criar/construir/verificar, e o que vai na API de Python contra o que vai nas tools do MCP. Use ao começar um projeto de CoppeliaSim, ao acrescentar um script a um existente, ou quando alguém perguntar por onde começar.
---

# Estrutura de um projeto de CoppeliaSim

Um projeto de CoppeliaSim que dá para entregar, repetir e corrigir tem uma forma
concreta. Esta skill descreve ela. Nada disso é estilo: cada peça resolve um
problema que aparece sempre.

## Antes de escrever código: o que vai onde

**Tudo que precisa ser reprodutível se escreve em Python** contra
`coppeliasim_zmqremoteapi_client`. Isso inclui construir a cena, montar o robô e
qualquer laço de controle.

**As tools do MCP são para olhar e conferir**, não para construir: listar
objetos, ler uma posição, disparar um sensor, ver se a simulação está rodando.
Um laço de controle não cabe nelas, e quarenta paredes são quarenta chamadas que
não deixam arquivo nenhum atrás.

Regra prática: se o resultado precisa sobreviver ao fechar o CoppeliaSim, vai
num script. Se é uma pergunta ("onde foi parar a parede?"), vai numa tool.

## Um script por artefato

Não coloque a cena, o robô e o controle no mesmo arquivo. Eles mudam em ritmos
diferentes: a cena se constrói uma vez, o robô se ajusta vinte vezes, e o
controle roda o tempo todo.

    cena.py        o mundo: chão, paredes, obstáculos
    robo.py        o robô dentro dela: chassi, juntas, sensores
    controle.py    o que o robô faz: teleoperação, navegação, a tarefa

Cada um roda sozinho e deixa a cena num estado conhecido.

## A ordem das funções

Os scripts seguem sempre a mesma sequência. Respeitar isso faz com que qualquer
pessoa — inclusive você daqui a um mês — saiba onde olhar.

```python
def conectar():
    return RemoteAPIClient(host=COPPELIA_HOST, port=COPPELIA_PORTA).require("sim")

def limpar(sim):
    """Apaga o que a rodada anterior deixou."""

def criar_peca(sim, ...):
    """Uma função por tipo de peça. Devolve o handle."""

def construir(sim):
    """Chama as criar_* em ordem e devolve o que foi construído."""

def verificar(...):
    """MEDE o resultado. Não supõe que deu certo."""

def main():
    sim = conectar()
    coisa = construir(sim)
    ok = verificar(coisa)
    if "--sem-salvar" not in sys.argv:
        sim.saveScene(CAMINHO_CENA)
    print("\nVeredito:", "pronto" if ok else "revisar")

if __name__ == "__main__":
    main()
```

### `limpar()` é o que torna o script re-executável

Sem ela, a segunda execução deixa duas casas sobrepostas. Apague a árvore inteira
do que você criou, não os objetos soltos:

```python
raiz = sim.getObject("/Casa")
arvore = set(sim.getObjectsInTree(raiz, sim.handle_all, 0)) | {raiz}
sim.removeObjects(list(arvore))
```

Envolva num `try/except`: na primeira execução não existe nada, e isso não é
erro.

Cuidado ao apagar por tipo em vez de por raiz: `/DefaultLights` e
`/XYZCameraProxy` são *dummies*, e apagá-los desmonta a cena padrão. Filtre
pelos tipos que você cria (`object_shape_type`, `object_joint_type`,
`object_proximitysensor_type`, `object_forcesensor_type`) e preserve o `/Floor`.

### `verificar()` é o que separa um projeto de um script

É a função mais omitida e a que mais vale. Não pergunte se parece certo:
**meça e deixe o script dar um veredito**.

- O robô passa pela porta? Rasterize as pegadas e confira a folga.
- Dá para chegar em todos os cômodos? Uma BFS sobre a grade responde.
- O sensor detecta? Ponha um obstáculo a três distâncias conhecidas e olhe.
- O robô anda reto? Trace a posição e compare com a teórica.

Um veredito impresso no fim transforma "acho que funciona" num dado.

## Configuração e flags

O host e a porta saem de um `.env` na raiz do projeto, com valores padrão que já
servem, para o script rodar sem configurar nada:

```python
load_dotenv(os.path.join(RAIZ_PROJETO, ".env"))
COPPELIA_HOST = os.getenv("COPPELIA_HOST", "127.0.0.1")
COPPELIA_PORTA = int(os.getenv("COPPELIA_PUERTO", "23000"))
```

Ancore o caminho no `__file__`, nunca no diretório de trabalho, ou o script só
vai funcionar lançado de uma pasta específica e vai falhar em silêncio de
qualquer outra.

Flags úteis, lidas do `sys.argv` sem precisar de `argparse`:

    --so-construir    constrói e pula os testes
    --sem-salvar      não sobrescreve o .ttt
    --foto            gera uma imagem do resultado

## O cabeçalho do módulo

A docstring do topo não deve repetir o óbvio: **anote as decisões e as medidas**
que condicionam todo o resto, com unidades. É ali que se explica por que o vão
tem 0,90 m e não 0,80, ou por que as rodas levam tanto atrito. Sem isso, o
próximo número que alguém mexer vai quebrar algo sem que se saiba por quê.

## Erros que se repetem

- Construir com `setObjectPosition` o que um motor deveria mover. Se o robô tem
  juntas, manda-se velocidade; empurrar na mão não é simular.
- Salvar a cena antes de verificar, e salvar assim uma cena quebrada.
- Colocar o laço de controle no mesmo script que constrói: cada ajuste de
  geometria obriga a repetir o teste inteiro.
- Deixar os caminhos dependerem do diretório de trabalho.
