from datetime import datetime
from fastapi import FastAPI
import pandas as pd
import yfinance as yf

app = FastAPI(
    title='B3 Options Quant API',
    version='1.0',
)

ativos_b3 = [
    'PETR4.SA',
    'VALE3.SA',
    'ITUB4.SA',
    'BBDC4.SA',
    'ABEV3.SA',
    'BBAS3.SA',
    'B3SA3.SA',
    'RENT3.SA',
    'WEGE3.SA',
    'ITSA4.SA',
    'SUZB3.SA',
    'RAIL3.SA',
    'RDOR3.SA',
    'GGBR4.SA',
    'PRIO3.SA',
    'EQTL3.SA',
    'UGPA3.SA',
    'RADL3.SA',
    'EMBR3.SA',
    'CMIG4.SA',
]

LETRAS_CALL = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']
LETRAS_PUT = ['M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X']


def obter_codigo_opcao(ticker_base, preco_atual, tipo='CALL'):
  agora = datetime.now()
  mes_atual = agora.month - 1
  letra = LETRAS_CALL[mes_atual] if tipo == 'CALL' else LETRAS_PUT[mes_atual]
  strike_int = int(round(preco_atual))
  strike_str = f'{strike_int:02d}0' if strike_int < 100 else f'{strike_int}'
  return f'{ticker_base}{letra}{strike_str}'


@app.get('/sinais-opcoes')
def obter_sinais_opcoes():
  resultados = []
  for ticker in ativos_b3:
    try:
      df = yf.download(
          ticker, period='30d', interval='60m', progress=False, auto_adjust=True
      )
      if df.empty or len(df) < 20:
        continue
      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
      df['EMA9_Dir'] = df['EMA9'].diff()

      ult = df.iloc[-1]
      ant = df.iloc[-2]
      preco = float(ult['Close'])
      ticker_limpo = ticker.replace('.SA', '')
      tend_alta = ult['EMA9_Dir'] > 0

      setup_ativado = 'Nenhum'
      if ant['EMA9_Dir'] < 0 and ult['EMA9_Dir'] > 0:
        setup_ativado = 'Setup 9.1 (Compra)'
      elif ant['EMA9_Dir'] > 0 and ult['EMA9_Dir'] < 0:
        setup_ativado = 'Setup 9.1 (Venda)'
      elif (
          tend_alta
          and (ult['Low'] < ant['Low'])
          and (ant['Low'] < df.iloc[-3]['Low'])
      ):
        setup_ativado = 'Setup 9.2 (Compra)'
      elif (
          tend_alta
          and (ult['Low'] <= ult['EMA9'] * 1.003)
          and (ult['Close'] > ult['Open'])
      ):
        setup_ativado = 'Ponto Contínuo - PC (Compra)'

      if setup_ativado != 'Nenhum':
        corpo_vela = abs(ult['Close'] - ult['Open'])
        amplitude = ult['High'] - ult['Low']
        forca_corpo = (corpo_vela / amplitude) if amplitude > 0 else 0.5
        base_prob = 58.0 if '9.1' in setup_ativado else 62.0
        if 'PC' in setup_ativado:
          base_prob = 65.0
        prob_gain = min(round(base_prob + (forca_corpo * 5), 1), 79.0)

        op_atm_call = obter_codigo_opcao(ticker_limpo, preco, 'CALL')
        op_otm_call = obter_codigo_opcao(ticker_limpo, preco * 1.03, 'CALL')
        op_atm_put = obter_codigo_opcao(ticker_limpo, preco, 'PUT')
        op_otm_put = obter_codigo_opcao(ticker_limpo, preco * 0.97, 'PUT')

        if 'Compra' in setup_ativado:
          estrategia = (
              '🚀 Compra CALL a Seco'
              if ('9.1' in setup_ativado and forca_corpo >= 0.65)
              else '🛡️ Trava de Alta (Call)'
          )
          ordem = (
              f'Comprar {op_atm_call}'
              if 'A Seco' in estrategia
              else f'Comprar {op_atm_call} / Vender {op_otm_call}'
          )
          stop_ativo = round(min(ult['Low'], ult['EMA9']) * 0.995, 2)
          take_ativo = round(
              preco + ((preco - stop_ativo) * 2.0),
              2,
          )
        else:
          estrategia = (
              '🔻 Compra PUT a Seco'
              if ('9.1' in setup_ativado and forca_corpo >= 0.65)
              else '🛡️ Trava de Baixa (Put)'
          )
          ordem = (
              f'Comprar {op_atm_put}'
              if 'A Seco' in estrategia
              else f'Comprar {op_atm_put} / Vender {op_otm_put}'
          )
          stop_ativo = round(max(ult['High'], ult['EMA9']) * 1.005, 2)
          take_ativo = round(
              preco - ((stop_ativo - preco) * 2.0),
              2,
          )

        resultados.append({
            'ativo': ticker_limpo,
            'preco_atual': round(preco, 2),
            'setup': setup_ativado,
            'prob_gain': f'{prob_gain}%',
            'estrategia': estrategia,
            'ordem_b3': ordem,
            'vencimento': 'Série Mensal Corrente',
            'stop_loss_ativo': stop_ativo,
            'take_profit_ativo': take_ativo,
            'regra_stop_opcao': 'Desmontar se prêmio cair 40%',
            'regra_take_opcao': 'Realizar lucro ao atingir +60%',
        })
    except Exception:
      continue

  return {
      'status': 'sucesso',
      'atualizado_em': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
      'total_sinais': len(resultados),
      'dados': resultados,
  }
