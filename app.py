import base64
import json
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response
import psycopg2

app = Flask(__name__)
FICHEIRO_DADOS = "dados_amora.json"
DATABASE_URL = os.environ.get("DATABASE_URL")

# Credenciais de acesso à Área Admin
ADMIN_USER = "admin"
ADMIN_PASS = "amora2026"

PRODUTOS_INICIAIS = [
    {
        "id": 1,
        "nome": "Amorino",
        "categoria": "Elegantes",
        "preco": 15.50,
        "stock": 10,
        "descricao": "Colar artesanal de contas vermelhas intensas com detalhes e pendente de coração em aço inoxidável dourado.",
        "imagem": "/static/amorino.jpg",
        "destaque": "Novo"
    }
]

CUPÕES = {
    "AMORA10": 0.10,
    "BEMVINDA": 0.15
}

def get_db_connection():
    if not DATABASE_URL:
        return None
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url)

def carregar_dados():
    dados_padrao = {"produtos": PRODUTOS_INICIAIS, "encomendas": []}
    
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Tabela do catálogo / estado geral
            cur.execute("""
                CREATE TABLE IF NOT EXISTS loja_estado (
                    id INTEGER PRIMARY KEY,
                    dados JSONB NOT NULL
                );
            """)
            
            # Tabela limpa só para as encomendas
            cur.execute("""
                CREATE TABLE IF NOT EXISTS encomendas (
                    id INTEGER PRIMARY KEY,
                    data TEXT,
                    cliente_nome TEXT,
                    cliente_email TEXT,
                    cliente_telefone TEXT,
                    cliente_morada TEXT,
                    pagamento TEXT,
                    artigos TEXT,
                    notas TEXT,
                    total NUMERIC(10,2),
                    estado TEXT
                );
            """)
            conn.commit()
            
            cur.execute("SELECT dados FROM loja_estado WHERE id = 1;")
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO loja_estado (id, dados) VALUES (1, %s::jsonb);",
                    (json.dumps(dados_padrao, ensure_ascii=False),)
                )
                conn.commit()
                dados = dados_padrao
            else:
                dados = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            cur.close()
            conn.close()
        except Exception as e:
            print("Erro ao ligar ao Supabase:", e)
            dados = dados_padrao
    else:
        if not os.path.exists(FICHEIRO_DADOS):
            guardar_dados(dados_padrao)
            dados = dados_padrao
        else:
            with open(FICHEIRO_DADOS, "r", encoding="utf-8") as f:
                dados = json.load(f)

    for p in dados.get("produtos", []):
        p.setdefault("stock", 5)
    for e in dados.get("encomendas", []):
        e.setdefault("estado", "Pendente")
    return dados

def guardar_dados(dados):
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO loja_estado (id, dados)
                VALUES (1, %s::jsonb)
                ON CONFLICT (id) DO UPDATE SET dados = EXCLUDED.dados;
            """, (json.dumps(dados, ensure_ascii=False),))
            conn.commit()
            cur.close()
            conn.close()
            return
        except Exception as e:
            print("Erro ao guardar no Supabase:", e)

    with open(FICHEIRO_DADOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def guardar_encomenda_tabela(enc):
    if not DATABASE_URL:
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        resumo_artigos = ", ".join([f"{i['qtd']}x {i['nome']} ({i['detalhes']})" for i in enc["itens"]])
        cur.execute("""
            INSERT INTO encomendas (
                id, data, cliente_nome, cliente_email, cliente_telefone,
                cliente_morada, pagamento, artigos, notas, total, estado
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET estado = EXCLUDED.estado;
        """, (
            enc["id"],
            enc["data"],
            enc["cliente"].get("nome", ""),
            enc["cliente"].get("email", ""),
            enc["cliente"].get("telefone", ""),
            enc["cliente"].get("morada", ""),
            enc["pagamento"],
            resumo_artigos,
            enc.get("notas", ""),
            enc["total"],
            enc["estado"]
        ))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Erro ao gravar na tabela encomendas:", e)

# --- PROTEÇÃO DA ÁREA ADMIN ---
@app.before_request
def proteger_rotas_admin():
    if request.path.startswith("/admin"):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
            return Response(
                "Acesso restrito à administração da Amora Store.",
                401,
                {"WWW-Authenticate": 'Basic realm="Area Admin Amora Store"'}
            )

# --- ROTAS DA LOJA ---
@app.route("/")
def index():
    dados = carregar_dados()
    return render_template("index.html", produtos=dados["produtos"])

@app.route("/api/cupao", methods=["POST"])
def validar_cupao():
    codigo = request.json.get("codigo", "").strip().upper()
    if codigo in CUPÕES:
        return jsonify({"valido": True, "desconto": CUPÕES[codigo], "codigo": codigo})
    return jsonify({"valido": False, "mensagem": "Cupão inválido ou expirado."})

@app.route("/api/checkout", methods=["POST"])
def checkout():
    payload = request.json
    itens = payload.get("itens", [])
    if not itens:
        return jsonify({"sucesso": False, "mensagem": "O carrinho está vazio."}), 400

    dados = carregar_dados()

    for item in itens:
        for prod in dados["produtos"]:
            if prod["id"] == item["id"]:
                if prod["stock"] < item["qtd"]:
                    return jsonify({"sucesso": False, "mensagem": f"Stock insuficiente para {prod['nome']}."}), 400
                prod["stock"] -= item["qtd"]

    nova_encomenda = {
        "id": len(dados["encomendas"]) + 1001,
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "cliente": payload["cliente"],
        "pagamento": payload["pagamento"],
        "notas": payload.get("notas", ""),
        "cupao": payload.get("cupao", ""),
        "itens": itens,
        "total": payload["total"],
        "estado": "Pendente"
    }
    dados["encomendas"].insert(0, nova_encomenda)
    guardar_dados(dados)
    guardar_encomenda_tabela(nova_encomenda)

    return jsonify({
        "sucesso": True,
        "encomenda_id": nova_encomenda["id"],
        "total": nova_encomenda["total"],
        "mensagem": f"Encomenda #{nova_encomenda['id']} registada! Aguarda validação após pagamento."
    })

# --- PAINEL DE ADMINISTRAÇÃO ---
@app.route("/admin", methods=["GET", "POST"])
def admin():
    dados = carregar_dados()
    if request.method == "POST":
        novo_id = max([p["id"] for p in dados["produtos"]], default=0) + 1
        
        imagem_final = "/static/amorino.jpg"
        ficheiro_foto = request.files.get("foto")
        if ficheiro_foto and ficheiro_foto.filename != "":
            dados_binarios = ficheiro_foto.read()
            tipo_mime = ficheiro_foto.content_type or "image/jpeg"
            b64 = base64.b64encode(dados_binarios).decode("utf-8")
            imagem_final = f"data:{tipo_mime};base64,{b64}"

        novo_produto = {
            "id": novo_id,
            "nome": request.form["nome"],
            "categoria": request.form["categoria"],
            "preco": float(request.form["preco"]),
            "stock": int(request.form["stock"]),
            "descricao": request.form["descricao"],
            "imagem": imagem_final,
            "destaque": request.form["destaque"]
        }
        dados["produtos"].append(novo_produto)
        guardar_dados(dados)
        return redirect(url_for("admin"))

    faturacao = sum(e["total"] for e in dados["encomendas"])
    return render_template("admin.html", produtos=dados["produtos"], encomendas=dados["encomendas"], faturacao=faturacao)

@app.route("/admin/stock/<int:produto_id>", methods=["POST"])
def definir_stock(produto_id):
    dados = carregar_dados()
    novo_stock = int(request.form.get("stock", 0))
    for p in dados["produtos"]:
        if p["id"] == produto_id:
            p["stock"] = max(0, novo_stock)
    guardar_dados(dados)
    return redirect(url_for("admin"))

@app.route("/admin/estado/<int:encomenda_id>", methods=["POST"])
def mudar_estado(encomenda_id):
    dados = carregar_dados()
    novo_estado = request.form.get("estado")
    for e in dados["encomendas"]:
        if e["id"] == encomenda_id:
            e["estado"] = novo_estado
            guardar_encomenda_tabela(e)
    guardar_dados(dados)
    return redirect(url_for("admin"))

@app.route("/admin/apagar/<int:produto_id>")
def apagar_produto(produto_id):
    dados = carregar_dados()
    dados["produtos"] = [p for p in dados["produtos"] if p["id"] != produto_id]
    guardar_dados(dados)
    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
