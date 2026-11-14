# Rotas manuais do Traefik como subdomínios de um domínio local

Data: 2026-11-14
Status: aguardando aprovação

## Intenção

Gerenciar rotas HTTP do Traefik pelo painel, uma máquina por painel, de forma que
toda rota seja um subdomínio de um único domínio local (ex.: `home.arpa`). O nome
resolvido no navegador é feito pelo arquivo `hosts` da máquina; o painel exibe a
linha a adicionar. Sem TLS neste ciclo.

## Objetivos

- Um `BASE_DOMAIN` configurável por ambiente (default `home.arpa`).
- O formulário pede apenas o subdomínio (label DNS); o backend monta
  `<subdomínio>.<BASE_DOMAIN>`.
- O Traefik roteia por `Host()` no entrypoint `web` (HTTP, porta 80), lendo o
  arquivo dinâmico pelo file provider que ele já observa.
- CRUD manual de rotas continua: criar, listar, editar e remover.
- A lista mostra o FQDN e uma dica da linha de `hosts` (`127.0.0.1 <fqdn>`).
- Painel continua acessível em `http://localhost:8000`; rotas são para serviços.

## Não-objetivos

- Rotas automáticas derivadas de containers (abortado neste ciclo).
- TLS/ACME, certificado self-signed ou CA interna; wildcard de certificado.
- Editar `hosts` automaticamente (exige privilégio; caminho difere entre Windows
  e WSL).
- DNS wildcard local (dnsmasq/Pi-hole) ou forwarding no roteador.
- Múltiplos servidores/hosts por painel.
- Roteamento TCP (Postgres etc.) ou path-based routing.

## Anti-objetivos

- Gravar `certResolver` sem resolver configurado (hoje quebra TLS silenciosamente).
- Aceitar domínio livre ou nomes com ponto no campo de subdomínio.
- Deletar/alterar rotas que não foram criadas por esta versão.

## Restrições

- DNS do roteador não tem wildcard; a resolução é por `hosts` na máquina que
  navega. Uma máquina por painel, então basta um `hosts`.
- Traefik roda em container e publica apenas `:80` (e dashboard em
  `127.0.0.1:8080`).
- `BASE_DOMAIN` precisa ser um domínio local válido, sem esquema e sem barra.

## Abordagens consideradas

1. **TLS**: HTTP puro (escolhido), HTTPS self-signed (aviso em todo dispositivo) e
   HTTPS com CA interna (exige instalar CA raiz em cada dispositivo). HTTP puro
   entrega o roteamento agora e permite migrar depois de forma aditiva.
2. **Resolução DNS**: entradas estáticas no roteador, resolvedor local com
   wildcard, ou `hosts` na máquina (escolhido). `hosts` não depende de suporte do
   roteador e atende ao cenário de uma máquina; o custo é uma linha manual por
   rota.
3. **Entrada da rota**: domínio completo com validação de sufixo, ou apenas
   subdomínio composto com `BASE_DOMAIN` (escolhido). Menos erro de digitação e
   garante a regra "toda rota é subdomínio".
4. **Origem das rotas**: manual (escolhido) vs. derivada do nome de container
   (adiado; exigiria decidir protocolo/porta e reconciliação).

## Decisões

### Configuração

- Novo `BASE_DOMAIN` em `Settings` (`app/config.py`), default `home.arpa`.
  Normalização: `strip()`, `lower()`, remover ponto final; rejeitar vazio,
  esquema (`://`), barra ou espaço.
- `.env.example`, `.env.wsl.example` e `docs/deploy-wsl.md` passam a incluir
  `BASE_DOMAIN=home.arpa`.

### Modelo de rota

- `RouteConfig` troca `domain` por `subdomain` e perde `tls`.
- `subdomain` é normalizado (`strip().lower()`) e validado como label DNS:
  `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$` (sem ponto, sem hífen no início/fim,
  até 63 caracteres).
- `name` continua sendo o identificador da rota (usado em `/routes/{name}`);
  permanece validado por `NAME_RE`.
- `target_url` mantém a validação `http://` ou `https://`.

### Serviço Traefik

- `TraefikService(dynamic_dir, base_domain)`; `fqdn = f"{subdomain}.{base_domain}"`.
- `upsert_route` grava no arquivo existente `stackpilot-routes.yml`:
  - router: `rule: Host(\`<fqdn>\`)`, `service: <name>`, `entryPoints: ["web"]`;
  - service: `loadBalancer.servers[0].url = target_url`;
  - sem `tls` e sem `certResolver`.
- `list_routes` lê o `Host()` e remove o sufixo `.<base_domain>` para obter o
  subdomínio. Rotas cujo domínio não termina em `.<base_domain>` não são
  gerenciadas nem listadas; o arquivo não é reescrito por causa delas.
- `get_route` e `delete_route` seguem por `name`.

### HTTP e UI

- `app/routers/routes.py`: campo `subdomain` no formulário; monta `RouteConfig`.
- `app/templates/partials/route_list.html`: coluna "Subdomínio" exibindo o FQDN,
  link `http://<fqdn>`, sem coluna/badge de TLS.
- `app/templates/partials/route_edit_row.html`: input de subdomínio.
- `app/templates/dashboard.html`: remove toggle TLS e o contador "HTTPS"; a dica
  do `hosts` fica junto ao formulário de criação.
- `app/main.py`: remove o cálculo de `tls_routes` do contexto.

### Traefik

- `deploy/docker-compose.traefik.yml`: remove o entrypoint `websecure` e a
  publicação `443:443`; mantém `web` (:80), file provider com `watch` e dashboard
  em `127.0.0.1:8080`.

## O que fica a cargo de quem implementa

- Texto exato da dica de `hosts` (incluindo o aviso de usar o IP do host quando o
  navegador não for a própria máquina).
- Se a linha de `hosts` aparece por rota na tabela ou apenas como dica única na
  seção.
- Mensagens de erro de validação em português.
- Ajuste fino do layout da tabela após remover a coluna TLS.

## Verificação

- `pytest`: modelo (subdomínio válido/inválido), YAML gerado (rule, entrypoint
  `web`, ausência de `tls`/`certResolver`), rotas HTTP do painel, composição
  `BASE_DOMAIN`, assets de deploy (sem `443`/`websecure`, com `BASE_DOMAIN`).
- Manual: criar `grafana` → conferir `stackpilot-routes.yml`, adicionar
  `127.0.0.1 grafana.home.arpa` ao `hosts`, acessar `http://grafana.home.arpa`
  com o Traefik de pé.
