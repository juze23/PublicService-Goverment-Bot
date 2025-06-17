#!/usr/bin/env python3
"""
Script de inicialização para a interface web do chatbot
"""

import subprocess
import sys
import time
import requests
import os

def check_ollama():
    """Verifica se o Ollama está rodando."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        return response.status_code == 200
    except:
        return False

def check_model():
    """Verifica se o modelo llama2:latest está disponível."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = [m['name'] for m in response.json()['models']]
            return 'llama2:latest' in models
        return False
    except:
        return False

def main():
    print("🤖 Chatbot do Câmara Municipal do Porto - Interface Web")
    print("=" * 50)
    
    # Verificar se o Ollama está rodando
    print("🔍 Verificando Ollama...")
    if not check_ollama():
        print("❌ Ollama não está rodando!")
        print("📝 Para iniciar o Ollama, execute em outro terminal:")
        print("   ollama run llama2:latest")
        print("\n💡 Se o Ollama não estiver instalado:")
        print("   1. Visite: https://ollama.ai")
        print("   2. Instale o Ollama")
        print("   3. Execute: ollama pull llama2:latest")
        print("   4. Execute: ollama run llama2:latest")
        return False
    
    print("✅ Ollama está rodando!")
    
    # Verificar se o modelo está disponível
    print("🔍 Verificando modelo...")
    if not check_model():
        print("❌ Modelo llama2:latest não encontrado!")
        print("📝 Para baixar o modelo, execute:")
        print("   ollama pull llama2:latest")
        return False
    
    print("✅ Modelo llama2:latest disponível!")
    
    # Iniciar o servidor web
    print("\n🚀 Iniciando servidor web...")
    print("📱 A interface estará disponível em: http://localhost:5000")
    print("⏹️  Pressione Ctrl+C para parar o servidor")
    print("-" * 50)
    
    try:
        # Importar e executar o app Flask
        from app import app
        app.run(debug=False, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n👋 Servidor parado pelo utilizador")
    except Exception as e:
        print(f"\n❌ Erro ao iniciar servidor: {e}")
        return False
    
    return True

if __name__ == "__main__":
    main() 