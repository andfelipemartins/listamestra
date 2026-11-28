def ativar_contrato(client, contrato):
    sessao = client.session
    sessao["contrato_ativo_id"] = contrato.pk
    sessao.save()
