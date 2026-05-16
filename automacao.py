import pandas as pd

dados = pd.read_excel("clientes.xlsx")

for index, linha in dados.iterrows():
    nome = linha["NOME"]
    valor = linha["VALOR"]

    mensagem = f"Olá {nome}, seu pagamento é R${valor}"

    print(mensagem)