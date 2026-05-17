import re
import io
import pandas as pd
import streamlit as st
import pdfplumber

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4


MAPEAMENTO_SOCIOS = {
    "FUCS": "André",
    "PIO SODALÍCIO": "André",
    "PIO SODALICIO": "André",
    "VIRVI RAMOS": "André",
    "CENTRO CLÍNICO PILTCHER": "Cristiano",
    "CENTRO CLINICO PILTCHER": "Cristiano",
    "SÃO JOÃO DA RESERVA": "Cristiano",
    "SAO JOAO DA RESERVA": "Cristiano",
}


def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def normalizar_texto(texto):
    return str(texto).strip().upper()


def identificar_socio(cliente):
    cliente_norm = normalizar_texto(cliente)

    for nome_cliente, socio in MAPEAMENTO_SOCIOS.items():
        if nome_cliente in cliente_norm:
            return socio

    return "Jovio"


def limpar_valor_brasileiro(valor):
    if pd.isna(valor):
        return 0.0

    valor = str(valor).replace("R$", "").strip()

    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")

    return pd.to_numeric(valor, errors="coerce")


def limpar_cliente(linha_participante):
    cliente = linha_participante.replace("Participante:", "").strip()
    cliente = re.split(r"\s+CNPJ:|\s+CPF:", cliente)[0].strip()
    return cliente


def ler_pdf_sci(arquivo):
    registros = []

    with pdfplumber.open(arquivo) as pdf:
        texto = "\n".join([pagina.extract_text() or "" for pagina in pdf.pages])

    linhas = texto.splitlines()
    nota_atual = None

    for linha in linhas:
        linha = linha.strip()

        padrao_nota = re.match(
            r"^(\d{2}/\d{2}/\d{4})\s+NFS-e\s+\d+\s+(\d+)\s+.*?\s+([\d\.]+,\d{2})\s+ISS",
            linha,
            re.IGNORECASE
        )

        if padrao_nota:
            if nota_atual:
                registros.append(nota_atual)

            nota_atual = {
                "nº nf": padrao_nota.group(2),
                "data": padrao_nota.group(1),
                "valor": padrao_nota.group(3),
                "cliente": "",
                "situação": "Válida",
            }

        elif linha.upper().startswith("PARTICIPANTE:") and nota_atual:
            nota_atual["cliente"] = limpar_cliente(linha)

        elif "CANCEL" in linha.upper() and nota_atual:
            nota_atual["situação"] = "Cancelada"

    if nota_atual:
        registros.append(nota_atual)

    df = pd.DataFrame(registros)

    if df.empty:
        st.error("Não consegui identificar notas fiscais no PDF.")
        st.stop()

    return df


def ler_arquivo_fiscal(arquivo):
    nome = arquivo.name.lower()

    if nome.endswith(".xlsx"):
        return pd.read_excel(arquivo)

    if nome.endswith(".pdf"):
        return ler_pdf_sci(arquivo)

    st.error("Formato não suportado.")
    st.stop()


def gerar_analise_offline(
    total_notas_emitidas,
    total_canceladas,
    faturamento_total,
    simples_total,
    totais_socio,
    totais_cliente
):
    socio_principal = totais_socio.sort_values("valor", ascending=False).iloc[0]
    cliente_principal = totais_cliente.sort_values("valor", ascending=False).iloc[0]

    participacao_principal = socio_principal["participação"]
    participacao_cliente = cliente_principal["valor"] / faturamento_total * 100

    analise = f"""
    O faturamento mensal válido totalizou {formatar_moeda(faturamento_total)}, com imposto do Simples Nacional informado de {formatar_moeda(simples_total)}.

    O sócio com maior participação no faturamento foi {socio_principal["sócio"]}, responsável por {participacao_principal:.1f}% do total faturado no período.

    O principal cliente do mês foi {cliente_principal["cliente"]}, representando {participacao_cliente:.1f}% do faturamento mensal.

    Foram identificadas {total_canceladas} nota(s) cancelada(s) entre {total_notas_emitidas} nota(s) emitida(s).

    Recomenda-se acompanhar a concentração de faturamento por cliente e por sócio, especialmente quando um único cliente ou sócio representar parcela relevante da receita mensal.

    Conclusão: o rateio do imposto foi realizado proporcionalmente ao faturamento de cada sócio, com base nas notas fiscais válidas do período.
    """

    return analise


def gerar_pdf(
    empresa,
    periodo,
    total_notas_emitidas,
    faturamento_total,
    simples_total,
    detalhamento,
    totais_socio,
    analise
):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()
    elementos = []

    elementos.append(Paragraph("<b>RELATÓRIO MENSAL GERENCIAL</b>", styles["Title"]))
    elementos.append(Spacer(1, 12))

    cabecalho = f"""
    <b>Empresa:</b> {empresa}<br/>
    <b>Período:</b> {periodo}<br/>
    <b>Total de notas emitidas:</b> {total_notas_emitidas}<br/>
    <b>Total faturado:</b> {formatar_moeda(faturamento_total)}<br/>
    <b>Total Simples Nacional:</b> {formatar_moeda(simples_total)}
    """

    elementos.append(Paragraph(cabecalho, styles["BodyText"]))
    elementos.append(Spacer(1, 20))

    elementos.append(Paragraph("<b>DETALHAMENTO DAS NOTAS</b>", styles["Heading2"]))

    tabela_detalhamento = [["NF", "Data", "Cliente", "Sócio", "Valor", "Imposto"]]

    for _, row in detalhamento.iterrows():
        tabela_detalhamento.append([
            str(row["nº nf"]),
            row["data"],
            row["cliente"],
            row["sócio"],
            formatar_moeda(row["valor"]),
            formatar_moeda(row["imposto"])
        ])

    tabela = Table(tabela_detalhamento, repeatRows=1)

    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]))

    elementos.append(tabela)
    elementos.append(Spacer(1, 20))

    elementos.append(Paragraph("<b>TOTAIS POR SÓCIO</b>", styles["Heading2"]))

    tabela_socios = [["Sócio", "Faturamento", "Imposto", "Participação"]]

    for _, row in totais_socio.iterrows():
        tabela_socios.append([
            row["sócio"],
            formatar_moeda(row["valor"]),
            formatar_moeda(row["imposto"]),
            f"{row['participação']:.1f}%"
        ])

    tabela2 = Table(tabela_socios)

    tabela2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))

    elementos.append(tabela2)
    elementos.append(Spacer(1, 20))

    elementos.append(Paragraph("<b>ANÁLISE GERENCIAL</b>", styles["Heading2"]))
    elementos.append(Paragraph(analise.replace("\n", "<br/>"), styles["BodyText"]))

    doc.build(elementos)

    pdf = buffer.getvalue()
    buffer.close()

    return pdf


st.set_page_config(page_title="Relatório Fiscal Offline", layout="wide")

st.title("Relatório Fiscal Gerencial Offline")

empresa = st.text_input("Empresa")
periodo = st.text_input("Período", placeholder="Ex.: Abril/2026")

simples_total = st.number_input(
    "Valor do Simples Nacional",
    min_value=0.0,
    step=0.01
)

arquivo = st.file_uploader(
    "Upload do livro fiscal",
    type=["xlsx", "pdf"]
)

if arquivo and empresa and periodo and simples_total > 0:

    df = ler_arquivo_fiscal(arquivo)

    total_notas_emitidas = len(df)

    df_validas = df[
        ~df["situação"].str.upper().str.contains("CANCEL", na=False)
    ].copy()

    df_validas["valor"] = df_validas["valor"].apply(limpar_valor_brasileiro)

    df_validas["data"] = pd.to_datetime(
        df_validas["data"],
        errors="coerce",
        dayfirst=True
    ).dt.strftime("%d/%m/%Y")

    df_validas["sócio"] = df_validas["cliente"].apply(identificar_socio)

    faturamento_total = df_validas["valor"].sum()

    if faturamento_total == 0:
        st.error("Faturamento total zerado. Verifique o arquivo.")
        st.stop()

    df_validas["imposto"] = (
        df_validas["valor"] / faturamento_total
    ) * simples_total

    totais_socio = (
        df_validas
        .groupby("sócio", as_index=False)
        .agg({
            "valor": "sum",
            "imposto": "sum"
        })
    )

    totais_socio["participação"] = (
        totais_socio["valor"] / faturamento_total
    ) * 100

    totais_cliente = (
        df_validas
        .groupby(["cliente", "sócio"], as_index=False)
        .agg({
            "valor": "sum",
            "imposto": "sum"
        })
    )

    total_canceladas = total_notas_emitidas - len(df_validas)

    analise = gerar_analise_offline(
        total_notas_emitidas,
        total_canceladas,
        faturamento_total,
        simples_total,
        totais_socio,
        totais_cliente
    )

    pdf = gerar_pdf(
        empresa,
        periodo,
        total_notas_emitidas,
        faturamento_total,
        simples_total,
        df_validas,
        totais_socio,
        analise
    )

    st.success("Relatório gerado com sucesso.")

    st.download_button(
        label="Baixar Relatório PDF",
        data=pdf,
        file_name=f"relatorio_{periodo.replace('/', '_')}.pdf",
        mime="application/pdf"
    )

    st.subheader("Notas extraídas")
    st.dataframe(df_validas)

    st.subheader("Totais por sócio")
    st.dataframe(totais_socio)