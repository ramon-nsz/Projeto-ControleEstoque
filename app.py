import sqlite3
from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime

app = Flask(__name__)
DB_NAME = "estoque_oficina.db"

# --- 1. CONFIGURAÇÃO DO BANCO DE DADOS ---
def iniciar_banco():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Tabela de Funcionários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS funcionarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL
        )
    ''')

    # Tabela de Materiais (COM ESPESSURA)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materiais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            espessura TEXT,  
            unidade TEXT NOT NULL, 
            saldo_atual INTEGER DEFAULT 0 
        )
    ''')
    
    # Tabela de Movimentações
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            quantidade INTEGER, 
            tipo TEXT, 
            destino_origem TEXT,
            funcionario_id INTEGER,
            data_registro DATETIME,
            FOREIGN KEY(material_id) REFERENCES materiais(id),
            FOREIGN KEY(funcionario_id) REFERENCES funcionarios(id)
        )
    ''')
    conn.commit()
    conn.close()


# ** CORREÇÃO CRÍTICA PARA O RENDER: INICIALIZAÇÃO E DADOS DE TESTE **
# O código aqui é executado sempre que o servidor é iniciado (Gunicorn/Render),
# garantindo que o banco de dados e as tabelas existam antes da primeira rota ser acessada.

iniciar_banco()

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# Adicionando Funcionários de Teste (APENAS SE A TABELA ESTIVER VAZIA)
cursor.execute("SELECT count(*) FROM funcionarios")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO funcionarios (nome) VALUES ('Guilherme - Compras')")
    cursor.execute("INSERT INTO funcionarios (nome) VALUES ('Ramon - Produção')")
    cursor.execute("INSERT INTO funcionarios (nome) VALUES ('Mauro - Encarregado')")
    cursor.execute("INSERT INTO funcionarios (nome) VALUES ('Junior - Dono')")
    print("Funcionários de teste inseridos!")
    
# Adicionando Materiais de Teste (APENAS SE A TABELA ESTIVER VAZIA)
cursor.execute("SELECT count(*) FROM materiais")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO materiais (nome, espessura, unidade, saldo_atual) VALUES ('ACM Preto Brilho', '0.18mm', 'Chapa', 0)")
    cursor.execute("INSERT INTO materiais (nome, espessura, unidade, saldo_atual) VALUES ('Acrílico Transparente', '3mm', 'M²', 0)")
    cursor.execute("INSERT INTO materiais (nome, espessura, unidade, saldo_atual) VALUES ('PVC Expandido', '10mm', 'Placa', 0)")
    print("Materiais de teste inseridos!")
    
conn.commit()
conn.close()

# --- 2. ROTAS DO SITE ---

@app.route('/')
def index():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Busca materiais com todas as colunas
    cursor.execute("SELECT id, nome, espessura, unidade, saldo_atual FROM materiais ORDER BY nome")
    materiais = cursor.fetchall()
    
    cursor.execute("SELECT * FROM funcionarios")
    funcionarios = cursor.fetchall()
    conn.close()
    
    error = request.args.get('error')
    success = request.args.get('success')
    
    return render_template('index.html', materiais=materiais, funcionarios=funcionarios, error=error, success=success)


# ROTA PARA RETIRADA DE MATERIAL EXISTENTE (SAÍDA)
@app.route('/movimentar_saida', methods=['POST'])
def movimentar_saida():
    material_id = request.form['material_id']
    destino = request.form['destino']
    funcionario_id = request.form['funcionario_id']
    
    try:
        # **VALIDAÇÃO: FORÇA A SER UM INTEIRO**
        quantidade = int(request.form['quantidade'])
        if quantidade <= 0:
            return redirect(url_for('index', error="A quantidade deve ser um inteiro positivo."))
    except ValueError:
        return redirect(url_for('index', error="Quantidade inválida. Apenas números inteiros são permitidos."))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Verifica saldo atual
    cursor.execute("SELECT saldo_atual FROM materiais WHERE id = ?", (material_id,))
    saldo_atual = cursor.fetchone()
    
    if saldo_atual is None:
        conn.close()
        return redirect(url_for('index', error="Material não encontrado."))
        
    if saldo_atual[0] < quantidade:
        conn.close()
        return redirect(url_for('index', error=f"Saldo insuficiente em estoque. Saldo atual: {saldo_atual[0]}"))

    # 1. Registra no histórico
    cursor.execute('''
        INSERT INTO movimentacoes (material_id, quantidade, tipo, destino_origem, funcionario_id, data_registro)
        VALUES (?, ?, 'SAIDA', ?, ?, ?)
    ''', (material_id, quantidade, destino, funcionario_id, datetime.now()))
    
    # 2. Atualiza o saldo
    cursor.execute("UPDATE materiais SET saldo_atual = saldo_atual - ? WHERE id = ?", (quantidade, material_id))
        
    conn.commit()
    conn.close()
    
    return redirect(url_for('index', success="Saída de material registrada com sucesso."))


# ROTA PARA ADICIONAR NOVO MATERIAL AO ESTOQUE (ENTRADA)
@app.route('/movimentar_entrada_novo', methods=['POST'])
def movimentar_entrada_novo():
    nome = request.form['nome'].strip()
    espessura = request.form['espessura'].strip()
    unidade = request.form['unidade']
    origem = request.form['origem']
    funcionario_id = request.form['funcionario_id']

    if not nome or not espessura or not origem:
        return redirect(url_for('index', error="Preencha todos os campos obrigatórios para o novo material."))
    
    try:
        # **VALIDAÇÃO: FORÇA A SER UM INTEIRO**
        quantidade = int(request.form['quantidade'])
        if quantidade <= 0:
            return redirect(url_for('index', error="A quantidade inicial deve ser um inteiro positivo."))
    except ValueError:
        return redirect(url_for('index', error="Quantidade inválida. Apenas números inteiros são permitidos."))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 1. Cria o novo material e define o saldo inicial
    cursor.execute('''
        INSERT INTO materiais (nome, espessura, unidade, saldo_atual)
        VALUES (?, ?, ?, ?)
    ''', (nome, espessura, unidade, quantidade))
    
    material_id = cursor.lastrowid # Pega o ID do material recém-criado

    # 2. Registra a primeira entrada no histórico
    cursor.execute('''
        INSERT INTO movimentacoes (material_id, quantidade, tipo, destino_origem, funcionario_id, data_registro)
        VALUES (?, ?, 'ENTRADA', ?, ?, ?)
    ''', (material_id, quantidade, origem, funcionario_id, datetime.now()))
        
    conn.commit()
    conn.close()
    
    return redirect(url_for('index', success="Novo material e entrada inicial registrados com sucesso."))


@app.route('/historico')
def historico():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    busca = request.args.get('busca', '')
    
    sql_query = '''
        SELECT 
            m.nome || ' (' || m.espessura || ')',  -- Concatena Nome e Espessura
            mo.quantidade, 
            mo.tipo, 
            mo.destino_origem, 
            f.nome, 
            mo.data_registro
        FROM movimentacoes mo
        JOIN materiais m ON mo.material_id = m.id
        JOIN funcionarios f ON mo.funcionario_id = f.id
    '''
    
    query_params = []
    
    if busca:
        sql_query += ' WHERE mo.destino_origem LIKE ?'
        query_params.append('%' + busca + '%')
        
    sql_query += ' ORDER BY mo.data_registro DESC'
    
    cursor.execute(sql_query, query_params)
    movimentacoes = cursor.fetchall()
    conn.close()
    
    return render_template('historico.html', movimentacoes=movimentacoes, busca=busca)

# --- 3. INICIALIZAÇÃO LOCAL (Opcional) ---
if __name__ == '__main__':
    # Este bloco é apenas para testar localmente no seu PC.
    app.run(debug=True)