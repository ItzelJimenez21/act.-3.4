import re
from flask import Flask, render_template, request, redirect, url_for
from difflib import get_close_matches

app = Flask(__name__)

# Definir patrones de tokens
patterns = {
    'PR': r'\b(programa|int|read|printf|end)\b',  # Eliminamos 'suma' de las palabras reservadas
    'ID': r'\b[a-zA-Z_][a-zA-Z0-9_]*\b',
    'NUM': r'\b\d+\b',
    'STRING': r'\"[^\"]*\"',
    'SYMBOL': r'[;:,.=(){}+\-*/]'
}

valid_tokens = ['programa', 'int', 'read', 'printf', 'end', ';', ':', ',', '=', '(', ')', '{', '}', '+', '-', '*', '/']
reserved_words = ['programa', 'int', 'read', 'printf', 'end']  # Eliminamos 'suma' de aquí

# Lista de variables conocidas
variables = []

# Contadores para los tipos de tokens
token_count = {
    'Palabra Reservada': 0,
    'Identificador': 0,
    'Variable': 0,
    'Número': 0,
    'Cadena': 0,
    'Símbolo': 0
}

# Función para reiniciar el contador
def reset_token_count():
    global token_count
    token_count = {
        'Palabra Reservada': 0,
        'Identificador': 0,
        'Variable': 0,
        'Número': 0,
        'Cadena': 0,
        'Símbolo': 0
    }

# Función para encontrar sugerencias de corrección de tokens
def find_closest_token(token):
    suggestion = get_close_matches(token, valid_tokens + reserved_words, n=1)
    return suggestion[0] if suggestion else None

# Función para validar si 'suma' está mal escrita
def validar_suma(token):
    if token == "sum":  # Detectar variaciones incorrectas de 'suma'
        return f"Se esperaba 'suma' en lugar de '{token}'"
    return None

# Función para verificar errores de llaves y paréntesis
def check_parentheses_and_braces(code):
    stack = []
    errors = []
    opening = {'(': ')', '{': '}'}
    closing = {')': '(', '}': '{'}

    for line_number, line in enumerate(code.splitlines(), start=1):
        for index, char in enumerate(line):
            if char in opening:
                stack.append((char, line_number))
            elif char in closing:
                if not stack or stack[-1][0] != closing[char]:
                    errors.append(f"Línea {line_number}: Falta apertura de '{char}'")
                else:
                    stack.pop()

    while stack:
        char, line_number = stack.pop()
        errors.append(f"Línea {line_number}: Falta cierre de '{char}'")

    return errors

# Función para verificar comas faltantes entre variables
def check_missing_commas(code):
    errors = []
    for line_number, line in enumerate(code.splitlines(), start=1):
        if 'int' in line:
            variables = line.split('int')[-1].split(';')[0]
            vars_list = variables.split(',')
            for i in range(len(vars_list) - 1):
                if vars_list[i].strip() and not vars_list[i+1].strip():
                    errors.append(f"Línea {line_number}: Falta una coma entre las variables.")
    return errors

# Función para verificar operadores faltantes entre variables
def check_missing_operators(code):
    errors = []
    for line_number, line in enumerate(code.splitlines(), start=1):
        # Excluir palabras reservadas y declaraciones válidas
        if any(keyword in line for keyword in reserved_words):
            continue
        # Excluir cadenas de texto
        if '"' in line:
            continue
        # Buscar patrones donde haya dos identificadores seguidos sin operador
        match = re.search(r'\b[a-zA-Z_][a-zA-Z0-9_]*\s+[a-zA-Z_][a-zA-Z0-9_]*\b', line)
        if match:
            errors.append(f"Línea {line_number}: Falta un operador entre '{match.group(0)}'.")
    return errors

# Función para verificar puntos y comas faltantes
def check_missing_semicolons(code):
    errors = []
    for line_number, line in enumerate(code.splitlines(), start=1):
        # Ignorar líneas en blanco o de apertura de bloques
        if not line.strip() or line.strip().endswith('{') or line.strip().startswith('}'):
            continue
        # Verificar que las líneas terminan con punto y coma, excepto las que contienen '{' o '}' al final
        if not line.strip().endswith(';') and not line.strip().endswith('{') and not line.strip().endswith('}'):
            errors.append(f"Línea {line_number}: Falta un punto y coma al final de la línea.")
    return errors

# Función para verificar declaraciones de variables sin tipo o mal estructuradas
def check_variable_declarations(code):
    errors = []
    for line_number, line in enumerate(code.splitlines(), start=1):
        stripped_line = line.strip()

        # Solo analizar líneas que comiencen con 'int' para detectar problemas en la declaración de variables
        if stripped_line.startswith('int'):
            # Verificar si la declaración de variables es correcta (formato correcto y termina en ';')
            if not re.match(r'int\s+[a-zA-Z_][a-zA-Z0-9_]*(\s*,\s*[a-zA-Z_][a-zA-Z0-9_]*)*\s*;', stripped_line):
                errors.append(f"Línea {line_number}: Declaración de variables mal estructurada o falta de punto y coma.")
            else:
                # Comprobar si faltan comas entre las variables
                variables_part = stripped_line[len('int'):].strip().rstrip(';')
                variables = [v.strip() for v in variables_part.split(',')]
                for var in variables:
                    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', var):
                        errors.append(f"Línea {line_number}: Variable mal declarada o falta de coma en la declaración de variables.")
    return errors

# Función para verificar funciones mal estructuradas
def check_function_calls(code):
    errors = []
    for line_number, line in enumerate(code.splitlines(), start=1):
        # Verificar si hay llamadas a funciones sin argumentos correctos, como "read a;" o cadenas sueltas como '("la suma es");'
        if re.search(r'^\([a-zA-Z0-9_]*\)\s*;$', line.strip()):
            errors.append(f"Línea {line_number}: Llamada a función mal estructurada o cadena fuera de una función.")
    return errors

def lex_analyze(code):
    tokens, errors = [], []
    lines = code.splitlines()
    for line_number, line in enumerate(lines, start=1):
        index = 0
        while index < len(line):
            if line[index].isspace():
                index += 1
                continue
            match = None
            for token_type, pattern in patterns.items():
                regex = re.compile(pattern)
                match = regex.match(line, index)
                if match:
                    token_value = match.group()
                    token_category, error_message, suggestion = categorize_token(token_value, token_type)

                    # Actualiza el contador de tokens según el tipo
                    if token_type == 'PR':
                        token_count['Palabra Reservada'] += 1
                    elif token_type == 'ID':
                        # Si el token es una variable, contarlo como variable
                        if token_value in variables:
                            token_count['Variable'] += 1
                        else:
                            token_count['Identificador'] += 1
                    elif token_type == 'NUM':
                        token_count['Número'] += 1
                    elif token_type == 'STRING':
                        token_count['Cadena'] += 1
                    elif token_type == 'SYMBOL':
                        token_count['Símbolo'] += 1

                    if error_message:
                        errors.append(f"Línea {line_number}: {error_message}")
                    tokens.append({
                        'line': line_number,
                        'token': token_value,
                        'palabra_reservada': 'X' if token_type == 'PR' else '',
                        'identificador': 'X' if token_type == 'ID' and token_value not in variables else '',
                        'variable': 'X' if token_value in variables else '',
                        'numero': 'X' if token_type == 'NUM' else '',
                        'cadena': 'X' if token_type == 'STRING' else '',
                        'simbolo': 'X' if token_type == 'SYMBOL' else '',
                        'tipo': token_category
                    })
                    index = match.end()
                    break
            if not match:
                token_value = line[index]
                errors.append(f"Línea {line_number}: Token inválido '{token_value}'")
                tokens.append({
                    'line': line_number,
                    'token': token_value,
                    'palabra_reservada': '',
                    'identificador': '',
                    'variable': '',
                    'numero': '',
                    'cadena': '',
                    'simbolo': '',
                    'tipo': 'Desconocido'
                })
                index += 1

    # Verificar llaves y paréntesis
    errors += check_parentheses_and_braces(code)

    # Verificar comas faltantes
    errors += check_missing_commas(code)

    # Verificar operadores faltantes
    errors += check_missing_operators(code)

    # Verificar puntos y comas faltantes
    errors += check_missing_semicolons(code)

    # Verificar declaración de variables sin tipo
    errors += check_variable_declarations(code)

    # Verificar funciones mal estructuradas
    errors += check_function_calls(code)

    return tokens, errors, token_count

# Modificación en la función categorize_token para validar 'suma'
def categorize_token(token, token_type):
    suma_error = validar_suma(token)
    if suma_error:  # Si hay un error con 'suma', notificarlo
        return 'Identificador inválido', suma_error, 'suma'
    
    if token_type == 'ID' and token not in valid_tokens and token not in reserved_words:
        suggestion = find_closest_token(token)
        if suggestion:
            return 'Identificador inválido', f"Se esperaba '{suggestion}' en lugar de '{token}'", suggestion
        else:
            # Agregar a la lista de variables si es una declaración de variables
            if token not in variables:
                variables.append(token)
            return 'Identificador', '', ''
    elif token_type == 'PR' and token not in reserved_words:
        suggestion = find_closest_token(token)
        return 'Palabra reservada inválida', f"Se esperaba '{suggestion}' en lugar de '{token}'", suggestion
    return token_type.capitalize(), '', ''

@app.route('/')
def index():
    reset_token_count()  # Asegurarse de reiniciar el contador al cargar la página
    return render_template('interfaz.html', code='', tokens=[], errors=[], token_count=token_count)

@app.route('/analyze', methods=['POST'])
def analyze():
    code = request.form['code']
    tokens, errors, token_count = lex_analyze(code)
    return render_template('interfaz.html', tokens=tokens, code=code, errors=errors, token_count=token_count)

@app.route('/reset', methods=['POST'])
def reset():
    reset_token_count()  # Reiniciar el contador cuando se presiona el botón de reiniciar
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)