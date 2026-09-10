export const meta = {
  name: 'orquestrador-ml',
  description: 'Roda o plantao diario e ja dispara o especialista certo (cadastro, frete, concorrencia ou margem) para cada achado. So recomenda, nunca escreve na API do ML.',
  phases: [
    { title: 'Plantao', detail: 'varre todas as contas com credencial ativa' },
    { title: 'Diagnostico e decisao', detail: 'um especialista por achado, em paralelo' },
    { title: 'Estado real', detail: 'batimento do vigia e alertas criticos de 24h, para o painel Malha Zion' },
  ],
}

const ESTADO_REAL_SCHEMA = {
  type: 'object',
  properties: {
    vigia: {
      type: 'object',
      properties: {
        batimentoIso: { type: 'string' },
        subiuIso: { type: 'string' },
      },
      required: ['batimentoIso', 'subiuIso'],
    },
    alertas24h: {
      type: 'object',
      properties: {
        criticos: { type: 'number' },
        medios: { type: 'number' },
        porContaCriticos: {
          type: 'array',
          items: {
            type: 'object',
            properties: { slug: { type: 'string' }, n: { type: 'number' } },
            required: ['slug', 'n'],
          },
        },
      },
      required: ['criticos', 'medios', 'porContaCriticos'],
    },
  },
  required: ['vigia', 'alertas24h'],
}

const PLANTAO_SCHEMA = {
  type: 'object',
  properties: {
    contas: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          slug: { type: 'string' },
          cliente: { type: 'string' },
          calma: { type: 'boolean' },
          achados: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                tipo: { type: 'string', enum: ['cadastro', 'frete', 'concorrencia', 'campanha'] },
                titulo: { type: 'string' },
                detalhe: { type: 'string' },
              },
              required: ['tipo', 'titulo', 'detalhe'],
            },
          },
        },
        required: ['slug', 'cliente', 'calma', 'achados'],
      },
    },
  },
  required: ['contas'],
}

const DIAGNOSTICO_SCHEMA = {
  type: 'object',
  properties: {
    resumo: { type: 'string' },
    prioridade: { type: 'string', enum: ['alta', 'media', 'baixa'] },
    comando_sugerido: { type: 'string' },
    precisa_autorizacao: { type: 'boolean' },
  },
  required: ['resumo', 'prioridade', 'precisa_autorizacao'],
}

const AGENTE_POR_TIPO = {
  cadastro: 'ml-cadastro',
  frete: 'ml-frete',
  concorrencia: 'ml-concorrencia',
  campanha: 'ml-margem',
}

const TETO_ACHADOS = 12

phase('Plantao')

const plantaoPrompt = [
  'Rode o plantao diario para todas as contas do zion-ml que tem credencial ativa',
  '(.env ok em python cli.py contas). Para cada conta, diga se esta calma ou se tem',
  'algo que precisa de decisao hoje.',
  '',
  'Classifique CADA achado que precisa de decisao em exatamente um tipo:',
  '- "cadastro": anuncio pausado, em revisao, sem modo de envio, fora do ar, sem SKU/custo.',
  '- "frete": frete gratis nao libera, Mercado Envios sumiu, custo de envio estourou a margem.',
  '- "concorrencia": perdeu buy box, concorrente cruzou preco, canibalizacao entre contas de',
  '  DONOS DIFERENTES (nao conte contas-irma do mesmo cliente como concorrencia).',
  '- "campanha": campanha do ML abriu abaixo do piso combinado, ou promocao liberada que',
  '  precisa de decisao de entrar, nao entrar ou sair.',
  '',
  'NAO inclua como achado o que hoje voce classificaria como "pode esperar"',
  '(concorrencia normal subindo/descendo preco dentro do piso, canibalizacao entre',
  'contas-irma do mesmo cliente, campanha aberta com folga de piso). So o que exige',
  'decisao hoje entra na lista de achados.',
].join('\n')

const plantao = await agent(plantaoPrompt, {
  agentType: 'ml-plantao',
  schema: PLANTAO_SCHEMA,
  phase: 'Plantao',
})

const achados = []
for (const conta of plantao.contas || []) {
  for (const achado of conta.achados || []) {
    achados.push({ ...achado, slug: conta.slug, cliente: conta.cliente })
  }
}

let descartados = 0
let paraDiagnosticar = achados
if (achados.length > TETO_ACHADOS) {
  descartados = achados.length - TETO_ACHADOS
  paraDiagnosticar = achados.slice(0, TETO_ACHADOS)
  log(descartados + ' achado(s) ficaram de fora do diagnostico automatico (teto de ' + TETO_ACHADOS + '/execucao) - veja no plantao bruto.')
}

phase('Diagnostico e decisao')

const diagnosticos = achados.length === 0 ? [] : await parallel(
  paraDiagnosticar.map((achado) => async () => {
    const agentType = AGENTE_POR_TIPO[achado.tipo]
    if (!agentType) return null

    const prompt = [
      'Conta ' + achado.slug + ' (cliente ' + achado.cliente + ').',
      'Achado do plantao de hoje, tipo "' + achado.tipo + '": ' + achado.titulo + ' - ' + achado.detalhe,
      '',
      'Rode "cli.py checar ' + achado.slug + '" antes de investigar e confirme o nickname.',
      'Investigue e devolva o diagnostico ou a decisao para ESTE achado especifico.',
      'Nao escreva nada na conta - apenas analise e recomende, com o comando pronto',
      'para eu rodar depois se eu autorizar (marque precisa_autorizacao como true',
      'sempre que o comando sugerido escrever na API ou no banco).',
    ].join('\n')

    const resultado = await agent(prompt, {
      agentType,
      schema: DIAGNOSTICO_SCHEMA,
      label: achado.tipo + ':' + achado.slug,
      phase: 'Diagnostico e decisao',
    })

    return resultado ? { ...achado, ...resultado } : null
  })
)

const validos = diagnosticos.filter(Boolean)

const ordemPrioridade = { alta: 0, media: 1, baixa: 2 }
const porCliente = {}

for (const conta of plantao.contas || []) {
  if (!porCliente[conta.cliente]) porCliente[conta.cliente] = { calmas: [], achados: [] }
  if (conta.calma) porCliente[conta.cliente].calmas.push(conta.slug)
}

for (const achado of validos) {
  if (!porCliente[achado.cliente]) porCliente[achado.cliente] = { calmas: [], achados: [] }
  porCliente[achado.cliente].achados.push(achado)
}

for (const cliente of Object.keys(porCliente)) {
  porCliente[cliente].achados.sort(function (a, b) {
    const pa = ordemPrioridade[a.prioridade] === undefined ? 3 : ordemPrioridade[a.prioridade]
    const pb = ordemPrioridade[b.prioridade] === undefined ? 3 : ordemPrioridade[b.prioridade]
    return pa - pb
  })
}

phase('Estado real')

const estadoRealPrompt = [
  'Colete o estado real de dois componentes de apoio, para alimentar o painel',
  '"Malha Zion" (nao escreva em nada, so leia):',
  '',
  '1. Vigia: leia o conteudo de data/vigia.batimento (uma linha, ISO) e a',
  '   primeira linha de data/vigia.subiu (ISO). Devolva os dois como estao,',
  '   sem reformatar.',
  '2. Alertas criticos das ultimas 24h: rode',
  '   ".venv/Scripts/python.exe cli.py alertas --horas 24" (ou "python cli.py',
  '   alertas --horas 24" se o venv nao existir nesse ambiente). Cada linha',
  '   comeca com "!" (critico) ou "·" (informativo) e traz "[conta_slug]" logo',
  '   depois da hora. Conte o total de linhas "!" e o total de linhas "·", e',
  '   monte a lista de contas com alerta critico (slug + quantos "!" daquela',
  '   conta). Ignore linhas de continuacao (as que comecam com espaco ou "•"',
  '   detalhando um alerta anterior) - elas nao tem seu proprio "!"/"·".',
].join('\n')

const estadoReal = await agent(estadoRealPrompt, {
  schema: ESTADO_REAL_SCHEMA,
  phase: 'Estado real',
})

return {
  total_achados_do_plantao: achados.length,
  descartados_por_teto: descartados,
  por_cliente: porCliente,
  estado_real: estadoReal,
}
