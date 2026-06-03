import os
import subprocess
import sys

def run_command(command, cwd=None):
    print(f"Running: {command}")
    try:
        subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            check=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        sys.exit(1)

def setup_auth_frontend():
    frontend_dir = "frontend"
    if not os.path.exists(frontend_dir):
        print("Frontend directory not found. Please run setup.py first.")
        return

    # Install next-auth
    print("Installing next-auth...")
    # Assumes npm is in path. use string for command.
    # We should detect if yarn or npm or pnpm is used? 
    # setup_project.py used npm via npx create-next-app.
    run_command("npm install next-auth", cwd=frontend_dir)

    # Create auth route
    # app/api/auth/[...nextauth]/route.ts
    auth_dir = os.path.join(frontend_dir, "src", "app", "api", "auth", "[...nextauth]")
    # check if 'src' exists (create-next-app might use src dir or not depending on flags)
    # in setup_project.py we used --src-dir flag?
    # cmd = "npx -y create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias \"@/*\""
    # Yes, --src-dir used.
    
    if not os.path.exists(auth_dir):
        os.makedirs(auth_dir)
        print(f"Created {auth_dir}")

    route_ts_path = os.path.join(auth_dir, "route.ts")
    if not os.path.exists(route_ts_path):
        print("Creating route.ts...")
        with open(route_ts_path, "w") as f:
            f.write("""import NextAuth from "next-auth"
import CredentialsProvider from "next-auth/providers/credentials"

const handler = NextAuth({
  providers: [
    CredentialsProvider({
      name: 'Credentials',
      credentials: {
        username: { label: "Username", type: "text", placeholder: "jsmith" },
        password: { label: "Password", type: "password" }
      },
      async authorize(credentials, req) {
        // Post to backend login endpoint
        const res = await fetch("http://localhost:8000/token", {
          method: 'POST',
          body: new URLSearchParams({
            'username': credentials?.username || '',
            'password': credentials?.password || ''
          }),
          headers: { "Content-Type": "application/x-www-form-urlencoded" }
        })
        const user = await res.json()

        // If no error and we have user data, return it
        if (res.ok && user && user.access_token) {
            // decode token or just store it. 
            // For now, let's just return a dummy user object with the token?
            // NextAuth expects a User object {id, name, email...}
            return { id: "1", name: user.email, email: user.email, accessToken: user.access_token }
        }
        // Return null if user data could not be retrieved
        return null
      }
    })
  ],
  callbacks: {
      async jwt({ token, user }) {
          if (user) {
              token.accessToken = (user as any).accessToken
          }
          return token
      },
      async session({ session, token }) {
          (session as any).accessToken = token.accessToken
          return session
      }
  }
})

export { handler as GET, handler as POST }
""")
        print("Created auth route.ts")

if __name__ == "__main__":
    setup_auth_frontend()
