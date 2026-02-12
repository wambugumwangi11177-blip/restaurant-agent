import NextAuth from "next-auth"
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
