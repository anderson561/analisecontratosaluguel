# 📐 Spec: Critérios de Prontidão e Qualidade de Auditoria de Segurança (Security Audit Readiness)

Esta especificação define o padrão executivo e o gabarito de avaliação técnica que todo relatório de auditoria e parecer de segurança deve cumprir antes da entrega final.

## 1. Escala de Severidade (CVSS v3.1 / DREAD Mapping)

Toda vulnerabilidade relatada deve ser categorizada conforme a matriz oficial:

| Nível | Pontuação CVSS v3.1 | Definição e Impacto | Prazo Recomendado de Correção |
| :--- | :--- | :--- | :--- |
| **Crítico** | 9.0 - 10.0 | Exploração remota sem autenticação, RCE, perda total de dados/fundos. | Imédiato (SLA < 24h) |
| **Alto** | 7.0 - 8.9 | Quebra grave de autorização, exfiltração de dados sensíveis, escalada de privilégio. | Alta prioridade (SLA < 7 dias) |
| **Médio** | 4.0 - 6.9 | Negação de serviço parcial, IDOR limitado, vazamento moderado de informações. | Próxima Sprint (SLA < 30 dias) |
| **Baixo** | 0.1 - 3.9 | Má prática de configuração, falta de cabeçalhos de segurança (HSTS/CSP). | Correção planejada |
| **Info** | 0.0 | Oportunidade de refatoração, clareza de código ou otimização defensiva. | A critério do time |

## 2. Estrutura Padrão da Ficha de Vulnerabilidade
Cada achado do relatório deve conter obrigatoriamente os seguintes campos:

```markdown
### [TOB-SEC-001] Título Claro e Conciso da Vulnerabilidade
- **Severidade:** Crítica / Alta / Média / Baixa
- **CVSS v3.1 Vector:** CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H (9.8)
- **Componente Afetado:** `src/auth/jwt_validator.rs:line 42`
- **Categoria:** CWE-287 (Improper Authentication)

#### Descrição
Explicação técnica e detalhada de como a vulnerabilidade ocorre e qual a falha de lógica ou implementação no código.

#### Impacto
Consequências práticas para o negócio e para a infraestrutura caso um atacante explore esta falha.

#### Proof of Concept (PoC)
```python
# Script de reprodução determinístico do vetor de ataque
import requests
payload = {"user": "admin' --"}
response = requests.post("https://target/api/login", json=payload)
print(response.text)