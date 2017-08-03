package org.pantsbuild.tools.junit.impl.security;

import java.util.concurrent.Callable;

import org.junit.runner.Description;
import org.junit.runners.model.Statement;

public class WrapStatementWithSecurityManager extends Statement {
  private final JSecMgr jSecMgr;
  private final TestSecurityContext.ContextKey contextKey;
  private final Statement inner;

  public WrapStatementWithSecurityManager(JSecMgr jSecMgr, TestSecurityContext.ContextKey contextKey, Statement inner) {
    this.jSecMgr = jSecMgr;
    this.contextKey = contextKey;
    this.inner = inner;
  }

  @Override
  public void evaluate() throws Throwable {
    JSecMgr jSecMgr = (JSecMgr) System.getSecurityManager();
    if (jSecMgr == null) {
      inner.evaluate();
      return;
    }

    jSecMgr.withSettings(
        contextKey,
        new Callable<Void>() {
      @Override
      public Void call() {
        try {
          inner.evaluate();
        } catch (Throwable throwable) {
          // The runtime exception here is unwrapped and rethrown by withSettings
          // TODO come up with a better protocol
          throw new RuntimeException(throwable);
        }
        return null;
      }
    });
  }

  public static Statement wrappedStatement(Description description, Statement statement) {
    if (true){
      return statement;
    }
    JSecMgr jSecMgr = (JSecMgr) System.getSecurityManager();
    if (jSecMgr == null) {
      return statement;
    }

    return new WrapStatementWithSecurityManager(
        jSecMgr,
        new TestSecurityContext.ContextKey(description.getClassName()),
        statement);
  }
}
