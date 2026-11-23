import json
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response

app = Flask(__name__)
FICHEIRO_DADOS = "dados_amora.json"

# Credenciais de acesso à Área Admin (altera a palavra-passe se quiseres)
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

def carregar_dados():
    if not os.path.exists(FICHEIRO_DADOS):
        dados = {"produtos": PRODUTOS_INICIAIS, "encomendas": []}
        guardar_dados(dados)
        return dados
    with open(FICHEIRO_DADOS, "r", encoding="utf-8") as f:
        dados = json.load(f)
        for p in dados.get("produtos", []):
            p.setdefault("stock", 5)
        for e in dados.get("encomendas", []):
            e.setdefault("estado", "Pendente")
        return dados

def guardar_dados(dados):
    with open(FICHEIRO_DADOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

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

    # Verificar e descontar stock
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
        "estado": "Aguardar Pagamento"
    }
    dados["encomendas"].insert(0, nova_encomenda)
    guardar_dados(dados)

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
        novo_produto = {
            "id": novo_id,
            "nome": request.form["nome"],
            "categoria": request.form["categoria"],
            "preco": float(request.form["preco"]),
            "stock": int(request.form["stock"]),
            "descricao": request.form["descricao"],
            "imagem": request.form["imagem"] or "/static/amorino.jpg",
            "destaque": request.form["destaque"]
        }
        dados["produtos"].append(novo_produto)
        guardar_dados(dados)
        return redirect(url_for("admin"))

    faturacao = sum(e["total"] for e in dados["encomendas"])
    return render_template("admin.html", produtos=dados["produtos"], encomendas=dados["encomendas"], faturacao=faturacao)

@app.route("/admin/stock/<int:produto_id>/<int:delta>")
def alterar_stock(produto_id, delta):
    dados = carregar_dados()
    for p in dados["produtos"]:
        if p["id"] == produto_id:
            p["stock"] = max(0, p["stock"] + delta)
    guardar_dados(dados)
    return redirect(url_for("admin"))

@app.route("/admin/estado/<int:encomenda_id>", methods=["POST"])
def mudar_estado(encomenda_id):
    dados = carregar_dados()
    novo_estado = request.form.get("estado")
    for e in dados["encomendas"]:
        if e["id"] == encomenda_id:
            e["estado"] = novo_estado
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
