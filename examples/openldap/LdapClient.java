package io.h5k.k8s.examples.openldap;

import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;
import javax.naming.ldap.InitialLdapContext;
import javax.naming.ldap.LdapContext;

public class LdapClient {

    public static void main(String[] args) throws NamingException {

        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY, "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL, "ldap://openldap.platform-services.svc.cluster.local");
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL, "cn=admin,dc=h5k,dc=io");
        env.put(Context.SECURITY_CREDENTIALS, "91FotvAcvN3Ys06D7tshbMPZHIrIPwz7");

        LdapContext context = new InitialLdapContext(env, null);
        SearchControls searchControls = new SearchControls();
        searchControls.setSearchScope(SearchControls.SUBTREE_SCOPE);

        NamingEnumeration<SearchResult> results = context.search(
            "dc=h5k,dc=io",
            "(objectClass=*)",
            searchControls
        );

        while (results.hasMore()) {
            SearchResult searchResult = results.next();
            System.out.println(searchResult);
        }
    }
}
