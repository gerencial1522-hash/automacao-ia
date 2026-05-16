import pandas as pd
import streamlit as st
from openai import OpenAI

# SUA CHAVE API
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("Automação com IA")

arquivo = st.file_uploader("Envie a planilha", type=["xlsx"])

if arquivo is not None:

    dados = pd.read_excel(arquivo)

    st.subheader("Dados")
    st.dataframe(dados)

    total = dados["VALOR"].sum()

    st.metric("Valor total", f"R${total}")

    if st.button("Analisar com IA"):

        texto_planilha = dados.to_string()

        resposta = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Você é um analista financeiro."
                },
                {
                    "role": "user",
                    "content": f"""
                    Analise estes dados:

                    {texto_planilha}

                    Gere:
                    - resumo financeiro
                    - observações
                    - insights
                    """
                }
            ]
        )

        resultado = resposta.choices[0].message.content

        st.subheader("Resposta da IA")
        st.write(resultado)