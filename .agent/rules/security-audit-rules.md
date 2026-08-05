---
name: security-audit-rules
description: Diretrizes de governança, regras de tolerância zero e restrições inegociáveis para auditorias de segurança de código e arquitetura baseadas na abordagem Trail of Bits.
---

# 📜 Regras Globais: Segurança de Software e Auditoria de Código

## 🎯 Objetivo
Estabelecer salvaguardas e travas de segurança para proibir padrões conhecidos de vulnerabilidade, garantir a não inclusão de segredos no repositório e impor padrões rígidos de qualidade defensiva.

## 🚫 Proibições Absolutas (Tolerância Zero)

### 1. Segredos e Credenciais Hardcoded
* É terminantemente proibido manter chaves privadas, tokens de API, senhas, certificados ou hashes de autenticação gravados em arquivos de código ou configuração.

### 2. Primitivas Criptográficas Proprietárias ou Inseguras
* É proibida a implementação de algoritmos criptográficos próprios ("Roll your own crypto"). Deve-se exigir o uso exclusivo de bibliotecas auditadas (ex: OpenSSL, libsodium, SubtleCrypto).
* Proibido o uso de algoritmos obsoletos (MD5, SHA1, DES, RC4, RSA com chaves < 2048 bits).

### 3. Operações de Memória Inseguras e Eval()
* Em C/C++: Uso de funções banidas (`strcpy`, `strcat`, `sprintf`, `gets`) é veto automático de aprovação.
* Em linguagens dinâmicas: Uso de `eval()`, `exec()`, `unserialize()` ou parsing XML com entidades externas ativas (XXE) sem sanitização estrita é estritamente proibido.

### 4. Supressão Silenciosa de Erros
* Proibido o uso de blocos `catch` vazios ou que ignorem exceções de segurança/autenticação sem logging auditável.

## ⚠️ Travas Obrigatórias de Aceitação
1. Qualquer código contendo uma vulnerabilidade com pontuação **CVSS >= 7.0 (High/Critical)** bloqueia a esteira de CI/CD e não pode ser aprovado para produção.
2. Todo endpoint público deve ter limitação de taxa (Rate Limiting) e validação de schema de entrada na camada de borda.