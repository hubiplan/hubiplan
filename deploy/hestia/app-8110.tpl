#=========================================================================#
# HUBIplan hinter HestiaCP (nginx-Proxy-Vorlage, HTTP)                    #
# Kopieren nach /usr/local/hestia/data/templates/web/nginx/app-8110.tpl   #
# Leitet nur auf HTTPS um; Let's-Encrypt-Prüfung läuft über nginx.conf_*. #
#                                                                         #
# Aufgebaut nach den Standardvorlagen von HestiaCP 1.9.4                  #
# (nginx-Vorlagen, github.com/hestiacp/hestiacp, Commit aae8b2b),         #
# GPL-3.0; von Ralf Philipsen geändert für HUBIplan ab Oktober 2026,      #
# letzte Änderung 2026-11-08 (bei jeder Änderung anpassen, GPL § 5a).     #
# Diese Datei steht daher unter der GPL-3.0; Volltext in                  #
# LICENSE-GPL-3.0.txt daneben, Einordnung in docs/lizenzen.md.            #
#=========================================================================#

server {
	listen      %ip%:%proxy_port%;
	server_name %domain_idn% %alias_idn%;
	error_log   /var/log/%web_system%/domains/%domain%.error.log error;

	include %home%/%user%/conf/web/%domain%/nginx.forcessl.conf*;

	location ~ /\.(?!well-known\/|file) {
		deny all;
		return 404;
	}

	location / {
		return 301 https://$host$request_uri;
	}

	include %home%/%user%/conf/web/%domain%/nginx.conf_*;
}
